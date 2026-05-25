SIM            = icarus
TOPLEVEL_LANG  = verilog

opt ?= compute_core

ifeq ($(opt),interface)
VERILOG_SOURCES = $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL        = gelu_axi_stream_interface
COCOTB_TEST_MODULES = tb_axis_interface

else ifeq ($(opt),convin)
VERILOG_SOURCES = $(PWD)/rtl/fp32_to_q16.sv 
TOPLEVEL       			= fp32_to_q16
COCOTB_TEST_MODULES         = tb_fp32_to_q16

else ifeq ($(opt),convout)
VERILOG_SOURCES = $(PWD)/rtl/q16_to_fp32.sv 
TOPLEVEL       			= q16_to_fp32
COCOTB_TEST_MODULES         = tb_q16_to_fp32

else ifeq ($(opt),gelu)
  VERILOG_SOURCES     = $(PWD)/rtl/fp32_to_q16.sv \
                        $(PWD)/rtl/compute_core.sv \
                        $(PWD)/rtl/q16_to_fp32.sv \
                        $(PWD)/rtl/gelu_fp32.sv
  TOPLEVEL            = gelu_fp32
  COCOTB_TEST_MODULES = tb_gelu_fp32
else ifeq ($(opt),top)
VERILOG_SOURCES = $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv

TOPLEVEL = gelu_top
MODULE   = tb_top
else
VERILOG_SOURCES = $(PWD)/rtl/compute_core.sv
TOPLEVEL       = compute_core
COCOTB_TEST_MODULES         = tb_compute_core
endif

export PYTHONPATH := $(PWD)/tb:$(PYTHONPATH)

# Allow GTKWave dumps

COMPILE_ARGS   += -g2012

COCOTB_MAKEFILES := $(shell cocotb-config --makefiles)
include $(COCOTB_MAKEFILES)/Makefile.sim
