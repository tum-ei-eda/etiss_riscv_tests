# ETISS RISC-V Tests

Python script to run the [official RISC-V instruction test suite](https://github.com/riscv-software-src/riscv-tests) in ETISS.

## Prerequisites

- Built ETISS with `bare_etiss_processor`
- Built RISC-V test suite, see link above for instructions
- Python 3 with `elftools` and `tqdm` installed

## Usage

```
python test.py --help
usage: test.py [-h] [--arch ARCH] [--bits BITS] [--runlevel RUNLEVEL] [--ext EXT] [--virt VIRT] tests_dir etiss_exe

positional arguments:
  tests_dir            Path containing the compiled RISC-V test binaries
  etiss_exe            Path to bare_etiss_processor binary

options:
  -h, --help           show this help message and exit
  --arch ARCH          The ETISS architecture to test
  --bits BITS          Tests of which bitness to run. Can be '3264' for 32 and 64 bits.
  --runlevel RUNLEVEL  List of runlevels to test. Can be 'm', 's', 'u' or any combination.
  --ext EXT            List of standard extensions to test. Can be 'i', 'm', 'a', 'c', 'f', 'd', 'zfh' or any combination.
  --virt VIRT          Virtualization levels to test. Can be 'p', 'v' or both.
```