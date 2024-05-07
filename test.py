#!/usr/bin/env python3

import argparse
import datetime
import os
import pathlib
import subprocess
import tempfile
from collections import defaultdict
from enum import Flag
from functools import partial

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from tqdm.contrib.concurrent import process_map


class KeepLogType(Flag):
	NONE = 0
	STDOUT = 1
	STDERR = 2
	BOTH = 3

ETISS_CFG = """[StringConfigurations]
vp.elf_file={test_file}
vp.coredsl_coverage_path={test_file.stem}.csv
jit.type={jit}JIT
arch.cpu={arch}

[IntConfigurations]
simple_mem_system.memseg_origin_00=0x80000000
simple_mem_system.memseg_length_00=0x00100000
etiss.max_block_size=500

[BoolConfigurations]
simple_mem_system.print_dbus_access=true
jit.debug=true
jit.gcc.cleanup=true
jit.verify=false
etiss.exit_on_loop=true

[Plugin FileLogger]
plugin.filelogger.logaddr={logaddr}
plugin.filelogger.logmask=0xFFFFFFFF
plugin.filelogger.terminate_on_write=true

{trace_enable}[Plugin PrintInstruction]
"""


def find_symbol_address(sym_name, symbol_tables: "list[SymbolTableSection]"):
	for section in symbol_tables:
		for symbol in section.iter_symbols():
			if symbol.name == sym_name:
				return symbol.entry["st_value"]

	raise ValueError("symobl %s not found", sym_name)

def add_annotation(out_str, addr, text):
	a = f"0x{addr:016x}:"
	b = f"{text}\n{a}"
	return out_str.replace(a.encode("utf-8"), b.encode("utf-8"))

def log_streams(results_path, base_name, output, fail_addr: int=None, test_addrs: "dict[int, str]"=None, keep=KeepLogType.NONE):
	if output.stdout and KeepLogType.STDOUT in keep:
		with open(results_path / f"{base_name}.stdout", "wb") as f:
			out_str = output.stdout

			if fail_addr is not None:
				out_str = add_annotation(out_str, fail_addr, "----- fail above here -----")

			if test_addrs is not None:
				for addr, text in test_addrs.items():
					out_str = add_annotation(out_str, addr, f"----- {text} -----")

			f.write(out_str)

	if output.stderr and KeepLogType.STDERR in keep:
		with open(results_path / f"{base_name}.stderr", "wb") as f:
			f.write(output.stderr)

def run_test(test_args, args):
	test_file, arch, results_path = test_args

	with open(test_file, "rb") as f:
		elf = ELFFile(f)

		symbol_tables = [x for x in elf.iter_sections() if isinstance(x, SymbolTableSection)]

		logaddr = find_symbol_address("tohost", symbol_tables)
		try:
			failaddr = find_symbol_address("fail", symbol_tables)
		except:
			failaddr = 0

		test_addrs = {}

		for section in symbol_tables:
			for symbol in section.iter_symbols():
				test_addrs[symbol.entry["st_value"]] = symbol.name

	fname = (results_path / "config" / test_file.stem).with_suffix(".ini")
	with open(fname, "w") as f:
		f.write(ETISS_CFG.format(test_file=test_file, arch=arch, logaddr=logaddr, jit=args.jit.upper(), trace_enable="" if args.trace else ";"))

	try:
		etiss_proc = subprocess.run([args.etiss_exe, f"-i{fname}"], capture_output=True, timeout=args.timeout, check=True)

		output = etiss_proc.stdout.decode("utf-8")
		return_val = int(output.rsplit("ETISS: Warning: FileLogger", 1)[0].strip().split()[-1]) >> 1
		passed = return_val == 0

		ret = (passed, f"{return_val}")

		log_streams(results_path / ("pass" if passed else "fail"), test_file.stem, etiss_proc, failaddr, test_addrs, args.keep_output)

	except ValueError as e:
		ret = (False, "no result")
		log_streams(results_path / "fail", test_file.stem, etiss_proc, failaddr, test_addrs, args.keep_output)

	except subprocess.TimeoutExpired as e:
		ret = (False, "timeout")
		log_streams(results_path / "fail", test_file.stem, e, failaddr, test_addrs, args.keep_output)

	except subprocess.CalledProcessError as e:
		ret = (False, "etiss error")
		log_streams(results_path / "fail", test_file.stem, e, failaddr, test_addrs, args.keep_output)

	return arch, (test_file.stem, ret)

def main():
	p = argparse.ArgumentParser()

	p.add_argument("tests_dir", help="Path containing the compiled RISC-V test binaries")
	p.add_argument("etiss_exe", help="Path to bare_etiss_processor binary")
	p.add_argument("--arch", nargs="*", default="RISCV", help="The ETISS architecture(s) to test. Specify multiple architectures as a space-separated list.")
	p.add_argument("--bits", default="32", help="Tests of which bitness to run. Can be '3264' for 32 and 64 bits.")
	p.add_argument("--runlevel", default="u", help="List of runlevels to test. Can be 'm', 's', 'u' or any combination.")
	p.add_argument("--ext", default="imcfd", help="List of standard extensions to test. Can be 'i', 'm', 'a', 'c', 'f', 'd', 'zfh' or any combination.")
	p.add_argument("--virt", default="p", help="Virtualization levels to test. Can be 'p', 'v' or both.")
	p.add_argument("--timeout", default=10, type=int, help="Timeout to complete a test run, exceeding the timeout marks the test as failed.")
	p.add_argument("-j", "--threads", type=int, help="Number of parallel threads to start. Assume CPU core count if no value is provided.")
	p.add_argument("--jit", choices=["tcc", "gcc", "llvm"], default="tcc", help="Which ETISS JIT compiler to use.")
	p.add_argument("--keep-output", choices=[x.name.lower() for x in KeepLogType], default=KeepLogType.NONE.name.lower(), help="Save ETISS stdout/stderr to files")
	p.add_argument("--trace", action="store_true", help="Generate an instruction trace. Helpful for debugging.")

	args = p.parse_args()
	args.keep_output = KeepLogType[args.keep_output.upper()]

	begin = datetime.datetime.now().strftime("%y%m%d_%H%M%S")

	tests_path = pathlib.Path(args.tests_dir).resolve()
	results_paths = []

	for arch in args.arch:
		p = pathlib.Path(f"results_{begin}_{args.bits}-{args.runlevel}-{args.ext}-{args.virt}_{arch}")
		p.mkdir()
		(p / "fail").mkdir()
		(p / "pass").mkdir()
		(p / "config").mkdir()
		results_paths.append(p)

	tests_2 = []

	for n in tests_path.glob("*.dump"):
		filename = n.stem

		arch, virt, name = filename.split("-", 2)

		bit = arch[2:4]
		runlevel = arch[4]
		ext = arch[5:]

		if bit in args.bits and runlevel in args.runlevel and ext in args.ext and virt in args.virt:
			tests_2.append(filename)

	test_files = [tests_path / test_name for test_name in tests_2]
	test_args = []

	for arch, results_path in zip(args.arch, results_paths):
		test_args.extend([(test_file, arch, results_path) for test_file in test_files])

	test_fun = partial(run_test, args=args)

	try:
		results = (process_map(test_fun, test_args, max_workers=args.threads))
	except KeyboardInterrupt:
		print("terminated")
		return

	results_dict = defaultdict(list)

	for r in results:
		results_dict[r[0]].append(r[1])

	for arch, results_path in zip(args.arch, results_paths):
		with open(results_path / "pass.txt", "w") as pass_f, open(results_path / "fail.txt", "a") as fail_f:
			for name, (result, reason) in sorted(results_dict[arch]):
				f = pass_f if result else fail_f
				f.write(f"{name}: {reason}\n")

	fails = [r[1][1][0] for r in results].count(False)

	print(f"done, summary:\nexecuted {len(results)} tests\nfailed: {fails}")

	os.remove(gdb_conf_name)

if __name__ == "__main__":
	main()
