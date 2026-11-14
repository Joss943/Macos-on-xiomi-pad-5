/*
 * NabuNT36523HID: IOHIDDevice for the Xiaomi Pad 5 NT36523 touch panel.
 *
 * Binding is by C++ subclassing of IOHIDDevice from the SDK's Kernel.framework
 * headers, so the compiler lays out the vtable for the SDK it builds against.
 * No vtable slot is hard-coded. Build against the macOS 27 SDK to target
 * macOS 27; the CI job in this repository builds against the SDK installed on
 * its runner and reports which one.
 *
 * Provider: the device-tree nub of the touch controller under the GENI SPI
 * engine (QUPv3 wrapper 2 SE1, 0x00C84000). Memory index 0 must map the SE
 * registers. Optional properties on the provider:
 *   geni-clk-sel, geni-clk-div   SE clock source index and divider (u32)
 *   poll-interval-ms             report polling period, default 8 (u32)
 *
 * Reports are polled from a timer: no TLMM/PDC GPIO interrupt controller
 * exists for nabu in XNU yet, so the GPIO 39 touch interrupt cannot be used.
 * NOT TESTED ON HARDWARE. The controller also needs its firmware uploaded by
 * the host after power-on; that loader is not implemented (see README).
 */
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/hid/IOHIDDevice.h>
#include <libkern/OSByteOrder.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <mach/mach_time.h>

extern "C" {
#include "../geni_spi.h"
#include "../nabu_touch_hid.h"
#include "../nt36523.h"
}

/*
 * Since macOS 11 the SDK marks the in-kernel IOHIDDevice "deprecated: Use
 * DriverKit". It is still exported. A HIDDriverKit dext is not usable here:
 * it starts only once user space is up and needs Apple-granted DriverKit
 * entitlements. The warning is silenced for this subclass only.
 */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
class NabuNT36523HID : public IOHIDDevice {
	OSDeclareDefaultStructors(NabuNT36523HID);

	IOMemoryMap *seMap = nullptr;
	volatile uint8_t *seBase = nullptr;
	IOTimerEventSource *pollTimer = nullptr;
	IOBufferMemoryDescriptor *reportBuffer = nullptr;
	struct geni_spi spi = {};
	struct nt36523_fw_info fwInfo = {};
	struct nt36523_watchdog watchdog = {};
	struct nabu_touch_hid_state hidState = {};
	uint32_t pollMs = 8;
	uint64_t lastScanAbs = 0;
	bool controllerReady = false;

	static uint32_t mmioRead(void *context, uint32_t offset);
	static void mmioWrite(void *context, uint32_t offset, uint32_t value);
	static uint64_t mmioNow(void *context);
	static uint32_t numberProperty(IOService *provider, const char *key, uint32_t fallback);

	int readController(uint32_t address, uint8_t *out, size_t length);
	void poll(IOTimerEventSource *sender);

public:
	bool handleStart(IOService *provider) APPLE_KEXT_OVERRIDE;
	void handleStop(IOService *provider) APPLE_KEXT_OVERRIDE;
	IOReturn newReportDescriptor(IOMemoryDescriptor **descriptor) const APPLE_KEXT_OVERRIDE;
	OSString *newTransportString() const APPLE_KEXT_OVERRIDE;
	OSString *newManufacturerString() const APPLE_KEXT_OVERRIDE;
	OSString *newProductString() const APPLE_KEXT_OVERRIDE;
	OSNumber *newVendorIDNumber() const APPLE_KEXT_OVERRIDE;
	OSNumber *newProductIDNumber() const APPLE_KEXT_OVERRIDE;
	OSNumber *newPrimaryUsagePageNumber() const APPLE_KEXT_OVERRIDE;
	OSNumber *newPrimaryUsageNumber() const APPLE_KEXT_OVERRIDE;
	IOReturn getReport(IOMemoryDescriptor *report, IOHIDReportType reportType,
	    IOOptionBits options) APPLE_KEXT_OVERRIDE;
};

OSDefineMetaClassAndStructors(NabuNT36523HID, IOHIDDevice);
#pragma clang diagnostic pop

uint32_t
NabuNT36523HID::mmioRead(void *context, uint32_t offset)
{
	auto *self = static_cast<NabuNT36523HID *>(context);
	return *reinterpret_cast<volatile uint32_t *>(self->seBase + offset);
}

void
NabuNT36523HID::mmioWrite(void *context, uint32_t offset, uint32_t value)
{
	auto *self = static_cast<NabuNT36523HID *>(context);
	*reinterpret_cast<volatile uint32_t *>(self->seBase + offset) = value;
	__builtin_arm_dmb(0xB);   /* ISH: keep register writes ordered */
}

uint64_t
NabuNT36523HID::mmioNow(void *)
{
	uint64_t ns = 0;
	absolutetime_to_nanoseconds(mach_absolute_time(), &ns);
	return ns / 1000;
}

uint32_t
NabuNT36523HID::numberProperty(IOService *provider, const char *key, uint32_t fallback)
{
	OSNumber *number = OSDynamicCast(OSNumber, provider->getProperty(key));
	return number ? number->unsigned32BitValue() : fallback;
}

int
NabuNT36523HID::readController(uint32_t address, uint8_t *out, size_t length)
{
	uint8_t page[3];
	uint8_t tx[NT36523_REPORT_BYTES + 2];
	uint8_t rx[NT36523_REPORT_BYTES + 2];
	nt36523_build_set_page(address, page);
	int result = geni_spi_transfer(&spi, page, nullptr, sizeof(page));
	if (result != GENI_SPI_OK) {
		return result;
	}
	const size_t xfer = nt36523_build_read(address, length, tx, sizeof(tx));
	if (xfer == 0) {
		return GENI_SPI_EINVAL;
	}
	result = geni_spi_transfer(&spi, tx, rx, static_cast<uint32_t>(xfer));
	if (result != GENI_SPI_OK) {
		return result;
	}
	return nt36523_extract_read(rx, xfer, out, length);
}

bool
NabuNT36523HID::handleStart(IOService *provider)
{
	if (!IOHIDDevice::handleStart(provider)) {
		return false;
	}
	seMap = provider->mapDeviceMemoryWithIndex(0);
	if (seMap == nullptr) {
		IOLog("NabuNT36523HID: provider has no GENI SE register window\n");
		return false;
	}
	seBase = reinterpret_cast<volatile uint8_t *>(seMap->getVirtualAddress());
	spi.io = { this, mmioRead, mmioWrite, mmioNow };
	spi.timeout_us = 20000;
	int result = geni_spi_probe(&spi);
	if (result != GENI_SPI_OK) {
		IOLog("NabuNT36523HID: GENI SE not usable as SPI (%d); was the SPI SE firmware loaded?\n", result);
		return false;
	}
	struct geni_spi_config config = {};
	config.chip_select = 0;
	config.mode = 0;
	config.clk_sel = static_cast<uint8_t>(numberProperty(provider, "geni-clk-sel", 0));
	config.clk_div = static_cast<uint16_t>(numberProperty(provider, "geni-clk-div", 2));
	if (geni_spi_configure(&spi, &config) != GENI_SPI_OK) {
		return false;
	}

	uint8_t info[NT36523_FWINFO_BYTES] = { NT36523_EVENT_MAP_FWINFO };
	result = readController(NT36523_EVENT_BUF_ADDR | NT36523_EVENT_MAP_FWINFO, info + 1, sizeof(info) - 1);
	if (result != NT36523_OK || nt36523_parse_fw_info(info, sizeof(info), &fwInfo) != NT36523_OK || !fwInfo.valid) {
		IOLog("NabuNT36523HID: controller firmware info invalid (%d); firmware upload is required\n", result);
		return false;
	}
	IOLog("NabuNT36523HID: fw 0x%02x, %u x %u\n", fwInfo.fw_ver, fwInfo.abs_x_max, fwInfo.abs_y_max);
	nt36523_watchdog_init(&watchdog, NT36523_WATCHDOG_FRAMES);

	reportBuffer = IOBufferMemoryDescriptor::withCapacity(NABU_TOUCH_INPUT_REPORT_BYTES, kIODirectionNone);
	if (reportBuffer == nullptr) {
		return false;
	}
	pollMs = numberProperty(provider, "poll-interval-ms", 8);
	pollTimer = IOTimerEventSource::timerEventSource(this,
	    OSMemberFunctionCast(IOTimerEventSource::Action, this, &NabuNT36523HID::poll));
	if (pollTimer == nullptr || getWorkLoop()->addEventSource(pollTimer) != kIOReturnSuccess) {
		return false;
	}
	controllerReady = true;
	pollTimer->setTimeoutMS(pollMs);
	return true;
}

void
NabuNT36523HID::poll(IOTimerEventSource *sender)
{
	if (!controllerReady) {
		return;
	}
	uint8_t packet[NT36523_REPORT_BYTES] = { 0 };
	struct nt36523_frame frame;
	if (readController(NT36523_EVENT_BUF_ADDR, packet + 1, NT36523_REPORT_BYTES - 1) == NT36523_OK &&
	    nt36523_parse_report(packet, sizeof(packet), fwInfo.abs_x_max, fwInfo.abs_y_max,
	    NT36523_DEFAULT_MAX_PRESSURE, &frame) == NT36523_OK) {
		if (nt36523_watchdog_should_recover(&watchdog, &frame)) {
			IOLog("NabuNT36523HID: controller requests a firmware reload; not implemented\n");
		} else if (frame.kind == NT36523_FRAME_TOUCH) {
			uint64_t now = mach_absolute_time(), ns = 0;
			absolutetime_to_nanoseconds(now - lastScanAbs, &ns);
			lastScanAbs = now;
			const uint16_t scan = static_cast<uint16_t>((ns / 100000) & 0xFFFF);
			uint8_t *bytes = static_cast<uint8_t *>(reportBuffer->getBytesNoCopy());
			const size_t length = nabu_touch_hid_pack(&hidState, &frame, scan, bytes,
			    NABU_TOUCH_INPUT_REPORT_BYTES);
			if (length != 0) {
				reportBuffer->setLength(length);
				handleReport(reportBuffer, kIOHIDReportTypeInput, 0);
			}
		}
	}
	sender->setTimeoutMS(pollMs);
}

void
NabuNT36523HID::handleStop(IOService *provider)
{
	controllerReady = false;
	if (pollTimer != nullptr) {
		pollTimer->cancelTimeout();
		getWorkLoop()->removeEventSource(pollTimer);
		OSSafeReleaseNULL(pollTimer);
	}
	OSSafeReleaseNULL(reportBuffer);
	OSSafeReleaseNULL(seMap);
	seBase = nullptr;
	IOHIDDevice::handleStop(provider);
}

IOReturn
NabuNT36523HID::newReportDescriptor(IOMemoryDescriptor **descriptor) const
{
	uint8_t bytes[NABU_TOUCH_DESCRIPTOR_MAX];
	const size_t length = nabu_touch_hid_descriptor(fwInfo.abs_x_max, fwInfo.abs_y_max,
	    NT36523_DEFAULT_MAX_PRESSURE, bytes, sizeof(bytes));
	if (length == 0) {
		return kIOReturnError;
	}
	IOBufferMemoryDescriptor *buffer = IOBufferMemoryDescriptor::withBytes(bytes, length, kIODirectionNone);
	if (buffer == nullptr) {
		return kIOReturnNoMemory;
	}
	*descriptor = buffer;
	return kIOReturnSuccess;
}

IOReturn
NabuNT36523HID::getReport(IOMemoryDescriptor *report, IOHIDReportType reportType, IOOptionBits options)
{
	const uint8_t reportID = static_cast<uint8_t>(options & 0xFF);
	if (reportType != kIOHIDReportTypeFeature || reportID != NABU_TOUCH_FEATURE_REPORT_ID) {
		return kIOReturnUnsupported;
	}
	uint8_t feature[2];
	const size_t length = nabu_touch_hid_feature(feature, sizeof(feature));
	return report->writeBytes(0, feature, length) == length ? kIOReturnSuccess : kIOReturnNoSpace;
}

OSString *
NabuNT36523HID::newTransportString() const
{
	return OSString::withCString("SPI");
}

OSString *
NabuNT36523HID::newManufacturerString() const
{
	return OSString::withCString("Novatek");
}

OSString *
NabuNT36523HID::newProductString() const
{
	return OSString::withCString("NT36523 Touch Panel (Xiaomi Pad 5)");
}

OSNumber *
NabuNT36523HID::newVendorIDNumber() const
{
	return OSNumber::withNumber(0x0603u, 32);   /* Novatek USB vendor ID, informational */
}

OSNumber *
NabuNT36523HID::newProductIDNumber() const
{
	return OSNumber::withNumber(0x6523u, 32);
}

OSNumber *
NabuNT36523HID::newPrimaryUsagePageNumber() const
{
	return OSNumber::withNumber(0x0Du, 32);     /* Digitizer */
}

OSNumber *
NabuNT36523HID::newPrimaryUsageNumber() const
{
	return OSNumber::withNumber(0x04u, 32);     /* Touch Screen */
}
