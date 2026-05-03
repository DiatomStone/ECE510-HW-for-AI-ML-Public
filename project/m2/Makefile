SIM            = icarus
TOPLEVEL_LANG  = verilog
VERILOG_SOURCES = $(PWD)/rtl/compute_core.sv 
TOPLEVEL       = compute_core
MODULE         = tb_compute_core
export PYTHONPATH := $(PWD)/tb:$(PYTHONPATH)
COMPILE_ARGS   += -g2012

include $(shell python3 -m cocotb_tools.config --makefiles)/Makefile.sim
