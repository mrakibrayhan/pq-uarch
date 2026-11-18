// ML-DSA (q = 8380417) multiply + Montgomery reduce unit (pq.dmul). Single-cycle combinational.
module pq_dmont(input [31:0] a, input [31:0] b, output [31:0] y);
  wire signed [63:0] p = $signed(a) * $signed(b);
  wire signed [31:0] t = p[31:0] * 32'sd58728449;            // QINV
  wire signed [63:0] r = (p - $signed(t) * 64'sd8380417) >>> 32;
  assign y = r[31:0];
endmodule
