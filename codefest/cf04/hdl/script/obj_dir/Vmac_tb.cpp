// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Model implementation (design independent parts)

#include "Vmac_tb__pch.h"

//============================================================
// Constructors

Vmac_tb::Vmac_tb(VerilatedContext* _vcontextp__, const char* _vcname__)
    : VerilatedModel{*_vcontextp__}
    , vlSymsp{new Vmac_tb__Syms(contextp(), _vcname__, this)}
    , rootp{&(vlSymsp->TOP)}
{
    // Register model with the context
    contextp()->addModel(this);
}

Vmac_tb::Vmac_tb(const char* _vcname__)
    : Vmac_tb(Verilated::threadContextp(), _vcname__)
{
}

//============================================================
// Destructor

Vmac_tb::~Vmac_tb() {
    delete vlSymsp;
}

//============================================================
// Evaluation function

#ifdef VL_DEBUG
void Vmac_tb___024root___eval_debug_assertions(Vmac_tb___024root* vlSelf);
#endif  // VL_DEBUG
void Vmac_tb___024root___eval_static(Vmac_tb___024root* vlSelf);
void Vmac_tb___024root___eval_initial(Vmac_tb___024root* vlSelf);
void Vmac_tb___024root___eval_settle(Vmac_tb___024root* vlSelf);
void Vmac_tb___024root___eval(Vmac_tb___024root* vlSelf);

void Vmac_tb::eval_step() {
    VL_DEBUG_IF(VL_DBG_MSGF("+++++TOP Evaluate Vmac_tb::eval_step\n"); );
#ifdef VL_DEBUG
    // Debug assertions
    Vmac_tb___024root___eval_debug_assertions(&(vlSymsp->TOP));
#endif  // VL_DEBUG
    vlSymsp->__Vm_deleter.deleteAll();
    if (VL_UNLIKELY(!vlSymsp->__Vm_didInit)) {
        VL_DEBUG_IF(VL_DBG_MSGF("+ Initial\n"););
        Vmac_tb___024root___eval_static(&(vlSymsp->TOP));
        Vmac_tb___024root___eval_initial(&(vlSymsp->TOP));
        Vmac_tb___024root___eval_settle(&(vlSymsp->TOP));
        vlSymsp->__Vm_didInit = true;
    }
    VL_DEBUG_IF(VL_DBG_MSGF("+ Eval\n"););
    Vmac_tb___024root___eval(&(vlSymsp->TOP));
    // Evaluate cleanup
    Verilated::endOfEval(vlSymsp->__Vm_evalMsgQp);
}

//============================================================
// Events and timing
bool Vmac_tb::eventsPending() { return !vlSymsp->TOP.__VdlySched.empty() && !contextp()->gotFinish(); }

uint64_t Vmac_tb::nextTimeSlot() { return vlSymsp->TOP.__VdlySched.nextTimeSlot(); }

//============================================================
// Utilities

const char* Vmac_tb::name() const {
    return vlSymsp->name();
}

//============================================================
// Invoke final blocks

void Vmac_tb___024root___eval_final(Vmac_tb___024root* vlSelf);

VL_ATTR_COLD void Vmac_tb::final() {
    Vmac_tb___024root___eval_final(&(vlSymsp->TOP));
}

//============================================================
// Implementations of abstract methods from VerilatedModel

const char* Vmac_tb::hierName() const { return vlSymsp->name(); }
const char* Vmac_tb::modelName() const { return "Vmac_tb"; }
unsigned Vmac_tb::threads() const { return 1; }
void Vmac_tb::prepareClone() const { contextp()->prepareClone(); }
void Vmac_tb::atClone() const {
    contextp()->threadPoolpOnClone();
}
