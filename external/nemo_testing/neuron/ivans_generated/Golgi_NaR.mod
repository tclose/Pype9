

TITLE Golgi_NaR


NEURON {
  RANGE NaR_h, NaR_m, comp313_vcbdur, comp313_vchdur, comp313_vcsteps, comp313_vcinc, comp313_vcbase, comp313_vchold, comp19_e, comp19_gbar
  RANGE i_NaR
  RANGE ina
  RANGE ena
  USEION na READ ena WRITE ina
}


FUNCTION comp19_beta_f (v, Q10) {
  comp19_beta_f  =  
  Q10 * comp19_Abeta_f * exp((v + -(comp19_V0beta_f)) / comp19_Kbeta_f)
}


FUNCTION comp19_beta_s (v, Q10) {
  LOCAL v462, v461
  v461  =  (v + comp19_V0beta_s) / comp19_Kbeta_s 
if (v461 > 200.0)  {v462  =  200.0} else {v462  =  v461} 
  comp19_beta_s  =  
      Q10 * 
          (comp19_Shiftbeta_s + 
              comp19_Abeta_s * 
                (v + comp19_V0beta_s) / (exp(v462) + -1.0))
}


FUNCTION comp19_alpha_f (v, Q10) {
  comp19_alpha_f  =  
  Q10 * comp19_Aalpha_f * 
    exp((v + -(comp19_V0alpha_f)) / comp19_Kalpha_f)
}


FUNCTION comp19_alpha_s (v, Q10) {
  comp19_alpha_s  =  
  Q10 * 
    (comp19_Shiftalpha_s + 
        (comp19_Aalpha_s * (v + comp19_V0alpha_s)) / 
          (exp((v + comp19_V0alpha_s) / comp19_Kalpha_s) + -1.0))
}


PARAMETER {
  comp19_Shiftalpha_s  =  8e-05
  comp313_vchold  =  -71.0
  comp19_V0alpha_s  =  -4.48754
  comp19_V0alpha_f  =  -80.0
  comp19_Kalpha_s  =  -6.81881
  comp19_Kalpha_f  =  -62.52621
  comp19_gbar  =  0.0017
  comp19_Aalpha_f  =  0.31836
  comp19_Aalpha_s  =  -0.00493
  comp313_vchdur  =  30.0
  comp19_Abeta_f  =  0.01014
  comp313_vcsteps  =  9.0
  comp313_vcbdur  =  100.0
  comp19_Abeta_s  =  0.01558
  comp19_V0beta_s  =  43.97494
  comp313_vcbase  =  -60.0
  comp19_V0beta_f  =  -83.3332
  comp19_Kbeta_s  =  0.10818
  comp19_Kbeta_f  =  16.05379
  comp19_Shiftbeta_s  =  0.04752
  comp313_vcinc  =  10.0
  comp19_e  =  87.39
}


STATE {
  NaR_mC
  NaR_mO
  NaR_hC
  NaR_hO
  NaR_m
  NaR_h
}


ASSIGNED {
  comp19_Q10
  celsius
  v
  ina
  ena
  i_NaR
}


PROCEDURE asgns () {
  comp19_Q10  =  3.0 ^ ((celsius + -20.0) / 10.0)
}


PROCEDURE reactions () {
  NaR_m  =  NaR_mO
  NaR_h  =  NaR_hO
}


BREAKPOINT {
  SOLVE states METHOD derivimplicit
  reactions ()
  i_NaR  =  (comp19_gbar * NaR_m * NaR_h) * (v - ena)
  ina  =  i_NaR
}


DERIVATIVE states {
  LOCAL v456, v459
  asgns ()
  v456  =  NaR_hO 
NaR_hO'  =  
    -(NaR_hO * comp19_beta_f(v, comp19_Q10)) + 
        (1 - v456) * (comp19_alpha_f(v, comp19_Q10))
  v459  =  NaR_mO 
NaR_mO'  =  
    -(NaR_mO * comp19_beta_s(v, comp19_Q10)) + 
        (1 - v459) * (comp19_alpha_s(v, comp19_Q10))
}


INITIAL {
  asgns ()
  NaR_m  =  
  (comp19_alpha_s(v, comp19_Q10)) / 
    (comp19_alpha_s(v, comp19_Q10) + comp19_beta_s(v, comp19_Q10))
  NaR_mO  =  NaR_m
  NaR_h  =  
  (comp19_alpha_f(v, comp19_Q10)) / 
    (comp19_alpha_f(v, comp19_Q10) + comp19_beta_f(v, comp19_Q10))
  NaR_hO  =  NaR_h
  ena  =  comp19_e
}


PROCEDURE print_state () {
  printf ("NMODL state: t = %g v = %g NaR_hO = %g\n" , t, v,  NaR_hO)
  printf ("NMODL state: t = %g v = %g NaR_mO = %g\n" , t, v,  NaR_mO)
  printf ("NMODL state: t = %g v = %g NaR_h = %g\n" , t, v,  NaR_h)
  printf ("NMODL state: t = %g v = %g NaR_m = %g\n" , t, v,  NaR_m)
}