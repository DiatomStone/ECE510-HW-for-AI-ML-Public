SIM            = icarus
TOPLEVEL_LANG  = verilog

opt ?= compute_core

ifeq ($(opt),interface)
VERILOG_SOURCES = $(PWD)/rtl/interface.sv $(PWD)/rtl/compute_core.sv
TOPLEVEL       = gelu_axi_stream_interface
MODULE         = tb_interface
else
VERILOG_SOURCES = $(PWD)/rtl/compute_core.sv
TOPLEVEL       = compute_core
MODULE         = tb_compute_core
endif

export PYTHONPATH := $(PWD)/tb:$(PYTHONPATH)
COMPILE_ARGS   += -g2012

include $(shell python3 -m cocotb_tools.config --makefiles)/Makefile.sim
