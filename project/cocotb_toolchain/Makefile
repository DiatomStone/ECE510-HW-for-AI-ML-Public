SIM ?= icarus
TOPLEVEL_LANG ?= verilog

# Compile ONLY the math engine core
VERILOG_SOURCES += $(PWD)/axis_accelerator.v

TOPLEVEL = axis_accelerator
MODULE = tb_hwsw_pipe_axis_test

include $(shell cocotb-config --makefiles)/Makefile.sim
