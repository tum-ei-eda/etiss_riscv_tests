#!/usr/bin/env python3

import argparse
import datetime
import os
import pathlib
import subprocess
import tempfile

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from tqdm import tqdm

ETISS_CFG = """[StringConfigurations]
vp.elf_file={test_file}
jit.type=TCCJIT
arch.cpu={arch}

[IntConfigurations]
simple_mem_system.memseg_origin_00=0x80000000
simple_mem_system.memseg_length_00=0x00100000

[Plugin Logger]
plugin.logger.logaddr={logaddr}
plugin.logger.logmask={logaddr}

[Plugin PrintInstruction]
"""

GDB_CFG = """set breakpoint pending on
break etiss::plugin::Logger::log
run
printf "done\\n"
x/wx buf
"""

def find_symbol_address(sym_name, elf_path):
	with open(elf_path, "rb") as f:
		elf = ELFFile(f)

		symbol_tables = [x for x in elf.iter_sections() if isinstance(x, SymbolTableSection)]

		for section in symbol_tables:
			for symbol in section.iter_symbols():
				if symbol.name == sym_name:
					return symbol.entry["st_value"]

	raise ValueError("symobl %s not found", sym_name)

def log_failure(results_dir, base_name, output, error):
	with open(results_dir / f"{base_name}.stdout", "wb") as f:
		f.write(output.stdout)
	with open(results_dir / f"{base_name}.stderr", "wb") as f:
		f.write(output.stderr)
	with open(results_dir / "fail.txt", "a") as f:
		f.write(f"{base_name}: {error}\n")

p = argparse.ArgumentParser()

p.add_argument("tests_dir", help="Path containing the compiled RISC-V test binaries")
p.add_argument("etiss_exe", help="Path to bare_etiss_processor binary")
p.add_argument("--arch", default="RISCV", help="The ETISS architecture to test")
p.add_argument("--bits", default="32", help="Tests of which bitness to run. Can be '3264' for 32 and 64 bits.")
p.add_argument("--runlevel", default="u", help="List of runlevels to test. Can be 'm', 's', 'u' or any combination.")
p.add_argument("--ext", default="imcfd", help="List of standard extensions to test. Can be 'i', 'm', 'a', 'c', 'f', 'd', 'zfh' or any combination.")
p.add_argument("--virt", default="p", help="Virtualization levels to test. Can be 'p', 'v' or both.")
p.add_argument("--timeout", default=5, type=int, help="Timeout to complete a test run, exceeding the timeout marks the test as failed.")
args = p.parse_args()

begin = datetime.datetime.now().strftime("%y%m%d_%H%M%S")

tests_path = pathlib.Path(args.tests_dir).resolve()
results_path = pathlib.Path(f"results_{begin}_{args.arch}")

results_path.mkdir()

tests_2 = []

fd, gdb_conf_name = tempfile.mkstemp(".gdb", "etiss_gdb_")

with open(fd, "w") as f:
	f.write(GDB_CFG)

for n in tests_path.glob("*.dump"):
	filename = n.stem

	arch, virt, name = filename.split("-", 2)

	bit = arch[2:4]
	runlevel = arch[4]
	ext = arch[5:]

	if bit in args.bits and runlevel in args.runlevel and ext in args.ext and virt in args.virt:
		tests_2.append(filename)

for test_name in tqdm(sorted(tests_2)):
	test_file = tests_path / test_name
	logaddr = find_symbol_address("tohost", test_file)

	fd, fname = tempfile.mkstemp(".ini", "etiss_dynamic_")
	with open(fd, "w") as f:
		f.write(ETISS_CFG.format(test_file=test_file, arch=args.arch, logaddr=logaddr))

	try:
		etiss_proc = subprocess.run(["gdb", "-batch", f"-command={gdb_conf_name}", "-args", args.etiss_exe, f"-i{fname}"], capture_output=True, timeout=args.timeout, check=True)

		output = etiss_proc.stdout.decode("utf-8")
		return_val = int(output.rsplit("done", 1)[-1].strip().split()[-1], 16)

		if return_val == 1:
			with open(results_path / "pass.txt", "a") as f:
				f.write(test_file.stem + "\n")
		else:
			log_failure(results_path, test_file.stem, etiss_proc, f"{return_val:08x}")

	except subprocess.TimeoutExpired as e:
		log_failure(results_path, test_file.stem, e, "timeout")

	except subprocess.CalledProcessError as e:
		log_failure(results_path, test_file.stem, e, "exc errro")

	os.remove(fname)

os.remove(gdb_conf_name)
