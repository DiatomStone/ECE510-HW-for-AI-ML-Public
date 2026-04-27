SIM            = icarus
TOPLEVEL_LANG  = verilog
VERILOG_SOURCES = $(PWD)/gelu.sv $(PWD)/dump_waves.sv
TOPLEVEL       = gelu
MODULE         = test_gelu
COMPILE_ARGS   += -g2012

include $(shell python3 -m cocotb_tools.config --makefiles)/Makefile.sim
