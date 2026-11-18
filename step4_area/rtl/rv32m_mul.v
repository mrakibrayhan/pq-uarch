// Reference: single-cycle 32x32 RV32M multiplier (mul/mulh/mulhsu/mulhu) for scale comparison.
module rv32m_mul(input [1:0] f, input [31:0] a, input [31:0] b, output [31:0] y);
  wire signed [32:0] sa = {(f == 2'd1 || f == 2'd2) & a[31], a};
  wire signed [32:0] sb = {(f == 2'd1) & b[31], b};
  wire signed [65:0] p = sa * sb;
  assign y = (f == 2'd0) ? p[31:0] : p[63:32];
endmodule
