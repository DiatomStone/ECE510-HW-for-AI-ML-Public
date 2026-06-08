SIM            = icarus
TOPLEVEL_LANG  = verilog

opt ?= compute_core

ifeq ($(opt),interface_x32)
VERILOG_SOURCES = $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL        = gelu_axi_stream_interface
COCOTB_TEST_MODULES = tb_interface

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

else ifeq ($(opt),inloop_x32)
VERILOG_SOURCES = $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv

TOPLEVEL            = gelu_top
COCOTB_TEST_MODULES = tb_top

else ifeq ($(opt),inloop_dma_x32)
VERILOG_SOURCES = $(PWD)/rtl/DMA_memory/gelu_dma_top.sv \
                  $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv \
                  $(PWD)/rtl/DMA_memory/mm2s_buffer.sv \
                  $(PWD)/rtl/DMA_memory/s2mm_buffer.sv

TOPLEVEL            = gelu_dma_top
COCOTB_TEST_MODULES = tb_top_inloop_dma

else ifeq ($(opt),mac)
VERILOG_SOURCES     = $(PWD)/rtl/sarray/mac.sv
TOPLEVEL            = mac
COCOTB_TEST_MODULES = tb_mac

else ifeq ($(opt),sarray)
VERILOG_SOURCES     = $(PWD)/rtl/sarray/systolic_array.sv \
                      $(PWD)/rtl/sarray/mac.sv
TOPLEVEL            = systolic_array
COCOTB_TEST_MODULES = tb_systolic_array

# x8 variants: same parameterized x32 RTL, but built at NUM_LANES=8 via the
# GELU_NUM_LANES macro (-D for Icarus) and the matching env var for the shared tb.
else ifeq ($(opt),interface_x8)
VERILOG_SOURCES = $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL            = gelu_axi_stream_interface
COCOTB_TEST_MODULES = tb_interface
COMPILE_ARGS       += -DGELU_NUM_LANES=8
export GELU_NUM_LANES := 8

else ifeq ($(opt),inloop_x8)
VERILOG_SOURCES = $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL            = gelu_top
COCOTB_TEST_MODULES = tb_top
COMPILE_ARGS       += -DGELU_NUM_LANES=8
export GELU_NUM_LANES := 8

else ifeq ($(opt),inloop_x1)
VERILOG_SOURCES = $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL            = gelu_top
COCOTB_TEST_MODULES = tb_top
COMPILE_ARGS       += -DGELU_NUM_LANES=1
export GELU_NUM_LANES := 1

else ifeq ($(opt),inloop_dma_x8)
VERILOG_SOURCES = $(PWD)/rtl/DMA_memory/gelu_dma_top.sv \
                  $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv \
                  $(PWD)/rtl/DMA_memory/mm2s_buffer.sv \
                  $(PWD)/rtl/DMA_memory/s2mm_buffer.sv
TOPLEVEL            = gelu_dma_top
COCOTB_TEST_MODULES = tb_top_inloop_dma
COMPILE_ARGS       += -DGELU_NUM_LANES=8
export GELU_NUM_LANES := 8

else ifeq ($(opt),inloop_dma_x1)
VERILOG_SOURCES = $(PWD)/rtl/DMA_memory/gelu_dma_top.sv \
                  $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv \
                  $(PWD)/rtl/DMA_memory/mm2s_buffer.sv \
                  $(PWD)/rtl/DMA_memory/s2mm_buffer.sv
TOPLEVEL            = gelu_dma_top
COCOTB_TEST_MODULES = tb_top_inloop_dma
COMPILE_ARGS       += -DGELU_NUM_LANES=1
export GELU_NUM_LANES := 1

# x16 variants: same parameterized RTL built at NUM_LANES=16 (512-bit bus).
else ifeq ($(opt),interface_x16)
VERILOG_SOURCES = $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL            = gelu_axi_stream_interface
COCOTB_TEST_MODULES = tb_interface
COMPILE_ARGS       += -DGELU_NUM_LANES=16
export GELU_NUM_LANES := 16

else ifeq ($(opt),inloop_x16)
VERILOG_SOURCES = $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv
TOPLEVEL            = gelu_top
COCOTB_TEST_MODULES = tb_top
COMPILE_ARGS       += -DGELU_NUM_LANES=16
export GELU_NUM_LANES := 16

else ifeq ($(opt),inloop_dma_x16)
VERILOG_SOURCES = $(PWD)/rtl/DMA_memory/gelu_dma_top.sv \
                  $(PWD)/rtl/top.sv \
                  $(PWD)/rtl/interface.sv \
                  $(PWD)/rtl/gelu_fp32.sv \
                  $(PWD)/rtl/compute_core.sv \
                  $(PWD)/rtl/fp32_to_q16.sv \
                  $(PWD)/rtl/q16_to_fp32.sv \
                  $(PWD)/rtl/DMA_memory/mm2s_buffer.sv \
                  $(PWD)/rtl/DMA_memory/s2mm_buffer.sv
TOPLEVEL            = gelu_dma_top
COCOTB_TEST_MODULES = tb_top_inloop_dma
COMPILE_ARGS       += -DGELU_NUM_LANES=16
export GELU_NUM_LANES := 16

else
VERILOG_SOURCES = $(PWD)/rtl/compute_core.sv
TOPLEVEL       = compute_core
COCOTB_TEST_MODULES         = tb_compute_core
endif

export PYTHONPATH := $(PWD)/tb:$(PWD)/tb/DMA_memory:$(PWD)/tb/sarray:$(PYTHONPATH)

# Allow GTKWave dumps

COMPILE_ARGS   += -g2012

COCOTB_MAKEFILES := $(shell cocotb-config --makefiles)
include $(COCOTB_MAKEFILES)/Makefile.sim
