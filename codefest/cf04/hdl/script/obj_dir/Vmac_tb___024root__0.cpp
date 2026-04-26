// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vmac_tb.h for the primary calling header

#include "Vmac_tb__pch.h"

VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__0(Vmac_tb___024root* vlSelf);
VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__1(Vmac_tb___024root* vlSelf);
VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__2(Vmac_tb___024root* vlSelf);

void Vmac_tb___024root___eval_initial(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_initial\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.mac_tb__DOT__clk = 0U;
    Vmac_tb___024root___eval_initial__TOP__Vtiming__0(vlSelf);
    Vmac_tb___024root___eval_initial__TOP__Vtiming__1(vlSelf);
    Vmac_tb___024root___eval_initial__TOP__Vtiming__2(vlSelf);
}

void Vmac_tb___024root____VbeforeTrig_h27d3174b__0(Vmac_tb___024root* vlSelf, const char* __VeventDescription);

VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__0(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_initial__TOP__Vtiming__0\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    IData/*31:0*/ mac_tb__DOT__expected;
    mac_tb__DOT__expected = 0;
    // Body
    vlSelfRef.mac_tb__DOT__rst = 1U;
    vlSelfRef.mac_tb__DOT__a = 0U;
    vlSelfRef.mac_tb__DOT__b = 0U;
    mac_tb__DOT__expected = 0U;
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         55);
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         56);
    vlSelfRef.mac_tb__DOT__rst = 0U;
    VL_WRITEF_NX("\n=== PHASE 1: a=3, b=4 for 3 cycles ===\n",0);
    vlSelfRef.mac_tb__DOT__a = 3U;
    vlSelfRef.mac_tb__DOT__b = 4U;
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         69);
    mac_tb__DOT__expected = ((IData)(0x0000000cU) + mac_tb__DOT__expected);
    vlSelfRef.__Vtask_mac_tb__DOT__check__0__label = "Cycle 1 | a= 3, b= 4"s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__0__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__0__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         70);
    mac_tb__DOT__expected = ((IData)(0x0000000cU) + mac_tb__DOT__expected);
    vlSelfRef.__Vtask_mac_tb__DOT__check__1__label = "Cycle 2 | a= 3, b= 4"s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__1__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__1__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         71);
    mac_tb__DOT__expected = ((IData)(0x0000000cU) + mac_tb__DOT__expected);
    vlSelfRef.__Vtask_mac_tb__DOT__check__2__label = "Cycle 3 | a= 3, b= 4"s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__2__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__2__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    VL_WRITEF_NX("\n=== PHASE 2: rst asserted (1 cycle) ===\n",0);
    vlSelfRef.mac_tb__DOT__rst = 1U;
    mac_tb__DOT__expected = 0U;
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         81);
    vlSelfRef.__Vtask_mac_tb__DOT__check__3__label = "Reset cycle           "s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__3__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__3__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    VL_WRITEF_NX("\n=== PHASE 3: a=-5, b=2 for 2 cycles ===\n",0);
    vlSelfRef.mac_tb__DOT__rst = 0U;
    vlSelfRef.mac_tb__DOT__a = 0xfbU;
    vlSelfRef.mac_tb__DOT__b = 2U;
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         93);
    mac_tb__DOT__expected = ((IData)(0xfffffff6U) + mac_tb__DOT__expected);
    vlSelfRef.__Vtask_mac_tb__DOT__check__4__label = "Cycle 1 | a=-5, b= 2"s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__4__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__4__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    Vmac_tb___024root____VbeforeTrig_h27d3174b__0(vlSelf, 
                                                  "@(posedge mac_tb.clk)");
    co_await vlSelfRef.__VtrigSched_h27d3174b__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(posedge mac_tb.clk)", 
                                                         "../mac_tb.sv", 
                                                         94);
    mac_tb__DOT__expected = ((IData)(0xfffffff6U) + mac_tb__DOT__expected);
    vlSelfRef.__Vtask_mac_tb__DOT__check__5__label = "Cycle 2 | a=-5, b= 2"s;
    co_await vlSelfRef.__VdlySched.delay(0x00000000000003e8ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         37);
    if (VL_UNLIKELY(((vlSelfRef.mac_tb__DOT__out != mac_tb__DOT__expected)))) {
        VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:39: Assertion failed in %Nmac_tb.check: [FAIL] %@ | got out=%0d, expected=%0d\n",0,
                     64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name(),
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__5__label),
                     32,vlSelfRef.mac_tb__DOT__out,
                     32,mac_tb__DOT__expected);
        VL_STOP_MT("../mac_tb.sv", 39, "");
    } else {
        VL_WRITEF_NX("[PASS] %@ | a=%0d, b=%0d, out=%0d\n",0,
                     -1,&(vlSelfRef.__Vtask_mac_tb__DOT__check__5__label),
                     8,(IData)(vlSelfRef.mac_tb__DOT__a),
                     8,vlSelfRef.mac_tb__DOT__b,32,
                     vlSelfRef.mac_tb__DOT__out);
    }
    VL_WRITEF_NX("\n=== Done. Final accumulator = %0d ===\n\n",0,
                 32,vlSelfRef.mac_tb__DOT__out);
    VL_FINISH_MT("../mac_tb.sv", 97, "");
    co_return;
}

VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__1(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_initial__TOP__Vtiming__1\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    co_await vlSelfRef.__VdlySched.delay(0x0000000000989680ULL, 
                                         nullptr, "../mac_tb.sv", 
                                         104);
    VL_WRITEF_NX("[%0t] %%Error: mac_tb.sv:105: Assertion failed in %Nmac_tb: TIMEOUT: simulation exceeded 10 us\n",0,
                 64,VL_TIME_UNITED_Q(1000),-9,vlSymsp->name());
    VL_STOP_MT("../mac_tb.sv", 105, "");
    VL_FINISH_MT("../mac_tb.sv", 106, "");
    co_return;
}

VlCoroutine Vmac_tb___024root___eval_initial__TOP__Vtiming__2(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_initial__TOP__Vtiming__2\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    while (VL_LIKELY(!vlSymsp->_vm_contextp__->gotFinish())) {
        co_await vlSelfRef.__VdlySched.delay(0x0000000000001388ULL, 
                                             nullptr, 
                                             "../mac_tb.sv", 
                                             29);
        vlSelfRef.mac_tb__DOT__clk = (1U & (~ (IData)(vlSelfRef.mac_tb__DOT__clk)));
    }
    co_return;
}

void Vmac_tb___024root___eval_triggers_vec__act(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_triggers_vec__act\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.__VactTriggered[0U] = (QData)((IData)(
                                                    ((vlSelfRef.__VdlySched.awaitingCurrentTime() 
                                                      << 1U) 
                                                     | ((IData)(vlSelfRef.mac_tb__DOT__clk) 
                                                        & (~ (IData)(vlSelfRef.__Vtrigprevexpr___TOP__mac_tb__DOT__clk__0))))));
    vlSelfRef.__Vtrigprevexpr___TOP__mac_tb__DOT__clk__0 
        = vlSelfRef.mac_tb__DOT__clk;
}

bool Vmac_tb___024root___trigger_anySet__act(const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___trigger_anySet__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        if (in[n]) {
            return (1U);
        }
        n = ((IData)(1U) + n);
    } while ((1U > n));
    return (0U);
}

void Vmac_tb___024root___nba_sequent__TOP__0(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___nba_sequent__TOP__0\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.mac_tb__DOT__out = ((IData)(vlSelfRef.mac_tb__DOT__rst)
                                   ? 0U : (vlSelfRef.mac_tb__DOT__out 
                                           + VL_MULS_III(32, 
                                                         VL_EXTENDS_II(32,8, (IData)(vlSelfRef.mac_tb__DOT__a)), 
                                                         VL_EXTENDS_II(32,8, (IData)(vlSelfRef.mac_tb__DOT__b)))));
}

void Vmac_tb___024root___eval_nba(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_nba\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1ULL & vlSelfRef.__VnbaTriggered[0U])) {
        vlSelfRef.mac_tb__DOT__out = ((IData)(vlSelfRef.mac_tb__DOT__rst)
                                       ? 0U : (vlSelfRef.mac_tb__DOT__out 
                                               + VL_MULS_III(32, 
                                                             VL_EXTENDS_II(32,8, (IData)(vlSelfRef.mac_tb__DOT__a)), 
                                                             VL_EXTENDS_II(32,8, (IData)(vlSelfRef.mac_tb__DOT__b)))));
    }
}

void Vmac_tb___024root___timing_ready(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___timing_ready\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1ULL & vlSelfRef.__VactTriggered[0U])) {
        vlSelfRef.__VtrigSched_h27d3174b__0.ready("@(posedge mac_tb.clk)");
    }
}

void Vmac_tb___024root___timing_resume(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___timing_resume\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.__VtrigSched_h27d3174b__0.moveToResumeQueue(
                                                          "@(posedge mac_tb.clk)");
    vlSelfRef.__VtrigSched_h27d3174b__0.resume("@(posedge mac_tb.clk)");
    if ((2ULL & vlSelfRef.__VactTriggered[0U])) {
        vlSelfRef.__VdlySched.resume();
    }
}

void Vmac_tb___024root___trigger_orInto__act_vec_vec(VlUnpacked<QData/*63:0*/, 1> &out, const VlUnpacked<QData/*63:0*/, 1> &in) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___trigger_orInto__act_vec_vec\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = (out[n] | in[n]);
        n = ((IData)(1U) + n);
    } while ((0U >= n));
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vmac_tb___024root___dump_triggers__act(const VlUnpacked<QData/*63:0*/, 1> &triggers, const std::string &tag);
#endif  // VL_DEBUG

bool Vmac_tb___024root___eval_phase__act(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_phase__act\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VactExecute;
    // Body
    Vmac_tb___024root___eval_triggers_vec__act(vlSelf);
    Vmac_tb___024root___timing_ready(vlSelf);
    Vmac_tb___024root___trigger_orInto__act_vec_vec(vlSelfRef.__VactTriggered, vlSelfRef.__VactTriggeredAcc);
#ifdef VL_DEBUG
    if (VL_UNLIKELY(vlSymsp->_vm_contextp__->debug())) {
        Vmac_tb___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
    }
#endif
    Vmac_tb___024root___trigger_orInto__act_vec_vec(vlSelfRef.__VnbaTriggered, vlSelfRef.__VactTriggered);
    __VactExecute = Vmac_tb___024root___trigger_anySet__act(vlSelfRef.__VactTriggered);
    if (__VactExecute) {
        vlSelfRef.__VactTriggeredAcc.fill(0ULL);
        Vmac_tb___024root___timing_resume(vlSelf);
    }
    return (__VactExecute);
}

bool Vmac_tb___024root___eval_phase__inact(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_phase__inact\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VinactExecute;
    // Body
    __VinactExecute = vlSelfRef.__VdlySched.awaitingZeroDelay();
    if (__VinactExecute) {
        VL_FATAL_MT("../mac_tb.sv", 3, "", "ZERODLY: Design Verilated with '--no-sched-zero-delay', but #0 delay executed at runtime");
    }
    return (__VinactExecute);
}

void Vmac_tb___024root___trigger_clear__act(VlUnpacked<QData/*63:0*/, 1> &out) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___trigger_clear__act\n"); );
    // Locals
    IData/*31:0*/ n;
    // Body
    n = 0U;
    do {
        out[n] = 0ULL;
        n = ((IData)(1U) + n);
    } while ((1U > n));
}

bool Vmac_tb___024root___eval_phase__nba(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_phase__nba\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    CData/*0:0*/ __VnbaExecute;
    // Body
    __VnbaExecute = Vmac_tb___024root___trigger_anySet__act(vlSelfRef.__VnbaTriggered);
    if (__VnbaExecute) {
        Vmac_tb___024root___eval_nba(vlSelf);
        Vmac_tb___024root___trigger_clear__act(vlSelfRef.__VnbaTriggered);
    }
    return (__VnbaExecute);
}

void Vmac_tb___024root___eval(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    IData/*31:0*/ __VnbaIterCount;
    // Body
    __VnbaIterCount = 0U;
    do {
        if (VL_UNLIKELY(((0x00000064U < __VnbaIterCount)))) {
#ifdef VL_DEBUG
            Vmac_tb___024root___dump_triggers__act(vlSelfRef.__VnbaTriggered, "nba"s);
#endif
            VL_FATAL_MT("../mac_tb.sv", 3, "", "DIDNOTCONVERGE: NBA region did not converge after '--converge-limit' of 100 tries");
        }
        __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
        vlSelfRef.__VinactIterCount = 0U;
        do {
            if (VL_UNLIKELY(((0x00000064U < vlSelfRef.__VinactIterCount)))) {
                VL_FATAL_MT("../mac_tb.sv", 3, "", "DIDNOTCONVERGE: Inactive region did not converge after '--converge-limit' of 100 tries");
            }
            vlSelfRef.__VinactIterCount = ((IData)(1U) 
                                           + vlSelfRef.__VinactIterCount);
            vlSelfRef.__VactIterCount = 0U;
            do {
                if (VL_UNLIKELY(((0x00000064U < vlSelfRef.__VactIterCount)))) {
#ifdef VL_DEBUG
                    Vmac_tb___024root___dump_triggers__act(vlSelfRef.__VactTriggered, "act"s);
#endif
                    VL_FATAL_MT("../mac_tb.sv", 3, "", "DIDNOTCONVERGE: Active region did not converge after '--converge-limit' of 100 tries");
                }
                vlSelfRef.__VactIterCount = ((IData)(1U) 
                                             + vlSelfRef.__VactIterCount);
                vlSelfRef.__VactPhaseResult = Vmac_tb___024root___eval_phase__act(vlSelf);
            } while (vlSelfRef.__VactPhaseResult);
            vlSelfRef.__VinactPhaseResult = Vmac_tb___024root___eval_phase__inact(vlSelf);
        } while (vlSelfRef.__VinactPhaseResult);
        vlSelfRef.__VnbaPhaseResult = Vmac_tb___024root___eval_phase__nba(vlSelf);
    } while (vlSelfRef.__VnbaPhaseResult);
}

void Vmac_tb___024root____VbeforeTrig_h27d3174b__0(Vmac_tb___024root* vlSelf, const char* __VeventDescription) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root____VbeforeTrig_h27d3174b__0\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Locals
    VlUnpacked<QData/*63:0*/, 1> __VTmp;
    // Body
    __VTmp[0U] = (QData)((IData)(((IData)(vlSelfRef.mac_tb__DOT__clk) 
                                  & (~ (IData)(vlSelfRef.__Vtrigprevexpr___TOP__mac_tb__DOT__clk__0)))));
    vlSelfRef.__Vtrigprevexpr___TOP__mac_tb__DOT__clk__0 
        = vlSelfRef.mac_tb__DOT__clk;
    if ((1ULL & __VTmp[0U])) {
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
        vlSelfRef.__VtrigSched_h27d3174b__0.ready(__VeventDescription);
    }
    vlSelfRef.__VactTriggeredAcc[0U] = (vlSelfRef.__VactTriggeredAcc[0U] 
                                        | __VTmp[0U]);
}

#ifdef VL_DEBUG
void Vmac_tb___024root___eval_debug_assertions(Vmac_tb___024root* vlSelf) {
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vmac_tb___024root___eval_debug_assertions\n"); );
    Vmac_tb__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    auto& vlSelfRef = std::ref(*vlSelf).get();
}
#endif  // VL_DEBUG
