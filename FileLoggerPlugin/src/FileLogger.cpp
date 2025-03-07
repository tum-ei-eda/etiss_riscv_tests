/*

        @copyright

        <pre>

        Copyright 2018 Infineon Technologies AG

        This file is part of ETISS tool, see <https://github.com/tum-ei-eda/etiss>.

        The initial version of this software has been created with the funding support by the German Federal
        Ministry of Education and Research (BMBF) in the project EffektiV under grant 01IS13022.

        Redistribution and use in source and binary forms, with or without modification, are permitted
        provided that the following conditions are met:

        1. Redistributions of source code must retain the above copyright notice, this list of conditions and
        the following disclaimer.

        2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions
        and the following disclaimer in the documentation and/or other materials provided with the distribution.

        3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse
        or promote products derived from this software without specific prior written permission.

        THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
        WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
        PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
        DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
        PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
        HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
        NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
        POSSIBILITY OF SUCH DAMAGE.

        </pre>

        @author Chair of Electronic Design Automation, TUM

        @version 0.1

*/

#include "FileLogger.h"
#include "etiss/jit/ReturnCode.h"

#include <cstring>

#include <iomanip>

namespace etiss
{

namespace plugin
{

// NOTE: no "pragma pack" needed since ETISS_System is already packed and this structure will not be accessed from
// runtime compiled code

// callbacks for system structure
// namespace {

namespace FileLoggerInternals
{

struct FileLoggerSystem
{

    struct ETISS_System sys;

    FileLogger *this_;

    ETISS_System *orig;

    uint64_t mask;
    uint64_t addr;
};

etiss_int32 iread(void *handle, ETISS_CPU *cpu, etiss_uint64 addr, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    if ((addr & lsys->mask) == lsys->addr)
    {
        return lsys->this_->log(true, addr & ~lsys->mask, 0, length);
    }
    ETISS_System *sys = lsys->orig;
    return sys->iread(sys->handle, cpu, addr, length);
}
etiss_int32 iwrite(void *handle, ETISS_CPU *cpu, etiss_uint64 addr, etiss_uint8 *buffer, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    if ((addr & lsys->mask) == lsys->addr)
    {
        return lsys->this_->log(false, addr & ~lsys->mask, buffer, length);
    }
    ETISS_System *sys = lsys->orig;
    return sys->iwrite(sys->handle, cpu, addr, buffer, length);
}

etiss_int32 dread(void *handle, ETISS_CPU *cpu, etiss_uint64 addr, etiss_uint8 *buffer, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    //	if ((addr&lsys->mask) == lsys->addr){
    //		return lsys->this_->log(true,addr&~lsys->mask,buffer,length);
    //	}
    //	std::cout <<  std::hex << addr << std::endl;
    ETISS_System *sys = lsys->orig;
    return sys->dread(sys->handle, cpu, addr, buffer, length);
}
etiss_int32 dwrite(void *handle, ETISS_CPU *cpu, etiss_uint64 addr, etiss_uint8 *buffer, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    if ((addr & lsys->mask) == lsys->addr)
    {
        return lsys->this_->log(false, addr & ~lsys->mask, buffer, length);
    }
    ETISS_System *sys = lsys->orig;
    return sys->dwrite(sys->handle, cpu, addr, buffer, length);
}

etiss_int32 dbg_read(void *handle, etiss_uint64 addr, etiss_uint8 *buffer, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    if ((addr & lsys->mask) == lsys->addr)
    {
        return lsys->this_->log(true, addr & ~lsys->mask, buffer, length);
    }
    ETISS_System *sys = lsys->orig;
    return sys->dbg_read(sys->handle, addr, buffer, length);
}

etiss_int32 dbg_write(void *handle, etiss_uint64 addr, etiss_uint8 *buffer, etiss_uint32 length)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    if ((addr & lsys->mask) == lsys->addr)
    {
        return lsys->this_->log(false, addr & ~lsys->mask, buffer, length);
    }
    ETISS_System *sys = lsys->orig;
    return sys->dbg_write(sys->handle, addr, buffer, length);
}

void syncTime(void *handle, ETISS_CPU *cpu)
{
    FileLoggerSystem *lsys = ((FileLoggerSystem *)handle);
    ETISS_System *sys = lsys->orig;
    sys->syncTime(sys->handle, cpu);
}

}
//}

FileLogger::FileLogger(uint64_t addr_value, uint64_t addr_mask, std::string output_file, std::string output_mode, bool terminate_on_write)
    : addr(addr_value & addr_mask),
      mask(addr_mask),
      terminate_on_write(terminate_on_write),
      output_mode(output_mode)
{
    if (output_file == "")
        this->output_file = &std::cout;
    else
        this->output_file = new std::ofstream(output_file);

    if (mask == 0 && addr == 0)
    {
        etiss::log(etiss::WARNING, "FileLogger instantiated with mask and address set to 0. this will redirect all "
                                   "read/writes exclusively to this logger instance.");
    }
}

ETISS_System *FileLogger::wrap(ETISS_CPU *cpu, ETISS_System *system)
{

    FileLoggerInternals::FileLoggerSystem *ret = new FileLoggerInternals::FileLoggerSystem();

    ret->sys.iread = &FileLoggerInternals::iread;
    ret->sys.iwrite = &FileLoggerInternals::iwrite;
    ret->sys.dread = &FileLoggerInternals::dread;
    ret->sys.dwrite = &FileLoggerInternals::dwrite;
    ret->sys.dbg_read = &FileLoggerInternals::dbg_read;
    ret->sys.dbg_write = &FileLoggerInternals::dbg_write;
    ret->sys.syncTime = &FileLoggerInternals::syncTime;

    ret->sys.handle = (void *)ret;

    ret->this_ = this;

    ret->orig = system;

    ret->addr = addr;
    ret->mask = mask;

    return (ETISS_System *)ret;
}

ETISS_System *FileLogger::unwrap(ETISS_CPU *cpu, ETISS_System *system)
{

    ETISS_System *ret = ((FileLoggerInternals::FileLoggerSystem *)system)->orig;

    delete system;

    return ret;
}

int32_t FileLogger::log(bool isread, uint64_t local_addr, uint8_t *buf, unsigned len)
{
    if (isread)
    {
        // memset(buf,0,len); //Produces segfault when iread is called!
        return 0;
    }

    if (len <= 0)
        return 0;

    if (buf == 0)
        return 0;

    uint64_t val;

    switch (len)
    {
    case 1:
        val = *buf;
        break;
    case 2:
        val = *(uint16_t*)buf;
        break;
    case 4:
        val = *(uint32_t*)buf;
        break;
    case 8:
        val = *(uint64_t*)buf;
        break;

    default:
        etiss::log(etiss::WARNING, "unsupported logger length");
        return 0;
        break;
    }

    *output_file << val << std::endl;
    output_file->flush();

    if (terminate_on_write) {
        etiss::log(etiss::WARNING, "FileLogger terminating");
        return etiss::RETURNCODE::CPUFINISHED;
    }

    return 0;
}

} // namespace plugin

} // namespace etiss
