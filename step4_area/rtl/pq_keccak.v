// Keccak-f[1600] unit (pq.keccak): 1600-bit state register, one round per cycle (24 cycles),
// state loaded/stored over a 32-bit port (50 words each way) -> ~124-cycle instruction.
module pq_keccak(input clk, input rst, input ld, input [5:0] widx, input [31:0] wdata,
                 input start, output busy, output [31:0] rdata);
  reg [1599:0] s; reg [4:0] rnd; reg run;
  function [63:0] rol(input [63:0] v, input integer n); rol = (n == 0) ? v : ((v << n) | (v >> (64 - n))); endfunction
  function [63:0] rc(input [4:0] i);
    case (i)
      0: rc=64'h0000000000000001; 1: rc=64'h0000000000008082; 2: rc=64'h800000000000808a; 3: rc=64'h8000000080008000;
      4: rc=64'h000000000000808b; 5: rc=64'h0000000080000001; 6: rc=64'h8000000080008081; 7: rc=64'h8000000000008009;
      8: rc=64'h000000000000008a; 9: rc=64'h0000000000000088; 10: rc=64'h0000000080008009; 11: rc=64'h000000008000000a;
      12: rc=64'h000000008000808b; 13: rc=64'h800000000000008b; 14: rc=64'h8000000000008089; 15: rc=64'h8000000000008003;
      16: rc=64'h8000000000008002; 17: rc=64'h8000000000000080; 18: rc=64'h000000000000800a; 19: rc=64'h800000008000000a;
      20: rc=64'h8000000080008081; 21: rc=64'h8000000000008080; 22: rc=64'h0000000080000001; default: rc=64'h8000000080008008;
    endcase
  endfunction
  integer x, y, k; reg [63:0] A [0:24]; reg [63:0] B [0:24]; reg [63:0] C [0:4]; reg [63:0] D; reg [1599:0] ns;
  localparam [199:0] RHO = {8'd14,8'd56,8'd61,8'd2,8'd18,8'd8,8'd21,8'd15,8'd45,8'd41,8'd39,8'd25,8'd43,8'd10,8'd3,8'd20,8'd55,8'd6,8'd44,8'd36,8'd27,8'd28,8'd62,8'd1,8'd0};
  always @* begin
    for (k = 0; k < 25; k = k + 1) A[k] = s[64*k +: 64];
    for (x = 0; x < 5; x = x + 1) C[x] = A[x] ^ A[x+5] ^ A[x+10] ^ A[x+15] ^ A[x+20];
    for (x = 0; x < 5; x = x + 1) begin D = C[(x+4)%5] ^ rol(C[(x+1)%5], 1); for (y = 0; y < 5; y = y + 1) A[x+5*y] = A[x+5*y] ^ D; end
    for (x = 0; x < 5; x = x + 1) for (y = 0; y < 5; y = y + 1) B[y + 5*((2*x+3*y)%5)] = rol(A[x+5*y], RHO[8*(x+5*y) +: 8]);
    for (x = 0; x < 5; x = x + 1) for (y = 0; y < 5; y = y + 1) A[x+5*y] = B[x+5*y] ^ (~B[(x+1)%5+5*y] & B[(x+2)%5+5*y]);
    A[0] = A[0] ^ rc(rnd);
    for (k = 0; k < 25; k = k + 1) ns[64*k +: 64] = A[k];
  end
  always @(posedge clk) begin
    if (rst) begin run <= 0; rnd <= 0; end
    else if (start) begin run <= 1; rnd <= 0; end
    else if (run) begin s <= ns; rnd <= rnd + 1; if (rnd == 23) run <= 0; end
    else if (ld) s[32*widx +: 32] <= wdata;
  end
  assign busy = run;
  assign rdata = s[32*widx +: 32];
endmodule
