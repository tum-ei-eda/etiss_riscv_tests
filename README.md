# ETISS RISC-V Tests

Python script to run the [official RISC-V instruction test suite](https://github.com/riscv-software-src/riscv-tests) in ETISS.

## Prerequisites

- Built ETISS with `bare_etiss_processor`
- Built RISC-V test suite, see link above for instructions
- Working `gdb` for your host platform
- Python 3.7 or newer

## Initial Steps
All steps assumed to be executed in the source directory of this project.

1) Create Python venv: `python -m venv venv`
2) Activate venv: `source venv/bin/activate`
3) Update venv: `pip install --upgrade pip setuptools wheel`
4) Install dependencies: `pip install -r requirements.txt`

## Usage

```
$ ./test.py -h
usage: test.py [-h] [--arch ARCH] [--bits BITS] [--runlevel RUNLEVEL] [--ext EXT] [--virt VIRT] [--timeout TIMEOUT] tests_dir etiss_exe

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
  --timeout TIMEOUT    Timeout to complete a test run, exceeding the timeout marks the test as failed.
```

## Output
A directory with the naming schema `results_<YYMMDD>_<hhmmss>_<ETISS_ARCH>` is created. In this directory, the file `pass.txt` indicates the names of passing tests. A separate file `fail.txt` contains the names and the reason of each failing test. Tests can fail for 3 reasons: The test case itself indicates failure, ETISS terminates prematurely, or ETISS does not terminate within a given timeframe (see Usage). For each failing test `stdout` and `stderr` of the underlying ETISS process are also saved to files.

## Working Principle
The RISC-V test suite programs contain small assembly language test cases verifying the correctness of instructions. At the end of each test, a result value is written to a special address denoted as `tohost` in the final ELF output. This script builds a list of all available test cases, filters them according to user preferences and executes ETISS for all remaining tests. The `tohost` output address is set as logging address in ETISS' logging plugin. To stop program execution once a test completes, ETISS is run in debug mode under `gdb` supervision. A breakpoint in the logging plugin output function stops ETISS on test completion and reads the return value of the test.
