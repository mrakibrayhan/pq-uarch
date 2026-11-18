// ML-KEM (q = 3329) Montgomery multiply / reduce / Barrett unit (pq.kmul, pq.kmred, pq.kbar)
// Combinational, single-cycle. Matches sim/rvsim.c kmred()/kbar().
module pq_kmont(input [1:0] op, input [31:0] a, input [31:0] b, output reg [31:0] y);
  wire signed [31:0] prod = $signed(a[15:0]) * $signed(b[15:0]);
  wire signed [31:0] x    = (op == 2'd0) ? $signed(a) : prod;            // kmred : kmul
  wire signed [15:0] t    = x[15:0] * -16'sd3327;                         // QINV
  wire signed [31:0] mr   = (x - $signed(t) * 32'sd3329) >>> 16;
  wire signed [31:0] bp   = 32'sd20159 * $signed(a[15:0]) + (32'sd1 << 25);
  wire signed [15:0] bq   = bp >>> 26;
  wire signed [15:0] br   = $signed(a[15:0]) - bq * 16'sd3329;
  always @* y = (op == 2'd2) ? {{16{br[15]}}, br} : {{16{mr[15]}}, mr[15:0]};
endmodule
