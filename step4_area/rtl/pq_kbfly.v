// ML-KEM packed butterfly unit: Cooley-Tukey (pq.kct) and Gentleman-Sande (pq.kgs)
// a = {r[j+len], r[j]} (16-bit lanes), b = zeta. Matches sim/rvsim.c.
module pq_kbfly(input gs, input [31:0] a, input [31:0] b, output [31:0] y);
  wire signed [15:0] lo = a[15:0], hi = a[31:16], z = b[15:0];
  wire signed [15:0] d  = hi - lo;
  wire signed [15:0] m  = gs ? d : hi;                       // shared Montgomery multiplier
  wire signed [31:0] p  = z * m;
  wire signed [15:0] t  = p[15:0] * -16'sd3327;
  wire signed [31:0] r  = (p - $signed(t) * 32'sd3329) >>> 16;
  wire signed [15:0] tt = r[15:0];
  wire signed [15:0] s  = lo + hi;                            // GS: Barrett(lo + hi)
  wire signed [31:0] bp = 32'sd20159 * s + (32'sd1 << 25);
  wire signed [15:0] bq = bp >>> 26;
  wire signed [15:0] bs = s - bq * 16'sd3329;
  assign y = gs ? {tt, bs} : {lo - tt, lo + tt};
endmodule
