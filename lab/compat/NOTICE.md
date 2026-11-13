# Third-party notice

`arm64e_pauth.py` uses instruction-lowering rules cross-checked against
[`UniXNU-zeta`](https://github.com/none24smu/UniXNU-zeta), revision
`eb489285a1d9153872f00c93ebb519a269b249b5`, file
`scripts/zeta_userland_pauth.py`. The project license is BSD-2-Clause-Patent.
The module in this repository is independently formatted and includes its
own fail-closed error handling.

`patches/xnu-12377/0001-accept-authenticated-fixups-without-pac.patch` and
`patches/xnu-12377/0002-emulate-pauth-el0-el1-without-pac.patch` are source
patches for Apple's XNU 12377.121.6. XNU is licensed under Apple Public Source
License 2.0; the patches contain no Apple source file.

`nabu_pauth_emu.h` is original no-PAC compatibility code for the ARM64
instruction encodings listed in its decoder. It treats authentication as a
no-op over plain pointers and does not implement PAC security.

Copyright (c) 2026, UniXNU contributors. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

Subject to the terms and conditions of this license, each copyright holder
and contributor hereby grants to those receiving rights under this license a
perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable
(except for failure to satisfy the conditions of this license) patent license
to make, have made, use, offer to sell, sell, import, and otherwise transfer
this software, where that license applies only to claims necessarily infringed
by the contribution alone or its addition to the work of authorship.

Except as expressly stated above, no rights or licenses from any copyright
holder or contributor are granted. The software is provided "AS IS", without
express or implied warranties, including merchantability or fitness for a
particular purpose. In no event shall the copyright holder be liable for any
direct, indirect, incidental, special, exemplary or consequential damages.


