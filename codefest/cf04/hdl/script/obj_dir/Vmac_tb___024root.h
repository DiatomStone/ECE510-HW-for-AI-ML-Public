// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vmac_tb.h for the primary calling header

#ifndef VERILATED_VMAC_TB___024ROOT_H_
#define VERILATED_VMAC_TB___024ROOT_H_  // guard

#include "verilated.h"
#include "verilated_timing.h"


class Vmac_tb__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vmac_tb___024root final {
  public:

    // DESIGN SPECIFIC STATE
    CData/*0:0*/ mac_tb__DOT__clk;
    CData/*0:0*/ mac_tb__DOT__rst;
    CData/*7:0*/ mac_tb__DOT__a;
    CData/*7:0*/ mac_tb__DOT__b;
    CData/*0:0*/ __Vtrigprevexpr___TOP__mac_tb__DOT__clk__0;
    CData/*0:0*/ __VactPhaseResult;
    CData/*0:0*/ __VinactPhaseResult;
    CData/*0:0*/ __VnbaPhaseResult;
    IData/*31:0*/ mac_tb__DOT__out;
    IData/*31:0*/ __VactIterCount;
    IData/*31:0*/ __VinactIterCount;
    IData/*31:0*/ __Vi;
    VlUnpacked<QData/*63:0*/, 1> __VactTriggered;
    VlUnpacked<QData/*63:0*/, 1> __VactTriggeredAcc;
    VlUnpacked<QData/*63:0*/, 1> __VnbaTriggered;
    std::string __Vtask_mac_tb__DOT__check__0__label;
    std::string __Vtask_mac_tb__DOT__check__1__label;
    std::string __Vtask_mac_tb__DOT__check__2__label;
    std::string __Vtask_mac_tb__DOT__check__3__label;
    std::string __Vtask_mac_tb__DOT__check__4__label;
    std::string __Vtask_mac_tb__DOT__check__5__label;
    VlDelayScheduler __VdlySched;
    VlTriggerScheduler __VtrigSched_h27d3174b__0;

    // INTERNAL VARIABLES
    Vmac_tb__Syms* vlSymsp;
    const char* vlNamep;

    // CONSTRUCTORS
    Vmac_tb___024root(Vmac_tb__Syms* symsp, const char* namep);
    ~Vmac_tb___024root();
    VL_UNCOPYABLE(Vmac_tb___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
};


#endif  // guard
