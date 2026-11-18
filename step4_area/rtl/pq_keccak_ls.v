// Lane-serial Keccak-f[1600] unit for pq.keccak (compact variant).
// State lives in two 25 x 64-bit RAMs (A = state, B = rho/pi buffer); one 64-bit lane per cycle.
// Per round: 25 cycles theta column parity, 25 cycles theta+rho+pi (A -> B),
// 50 cycles chi+iota (B -> A, 5 lanes read then 5 written per row) = 100 cycles,
// 24 rounds = 2400 cycles, plus 50 + 50 cycles state transfer on the 32-bit port.
// The rho rotation uses one 64-bit barrel rotator; only C (5 lanes) and one row (5 lanes)
// are flip-flops. Author: Md. Rakib Rayhan
module pq_keccak_ls(input clk, input rst,
                    input ld, input [5:0] widx, input [31:0] wdata,   // 32-bit state port
                    input start, output busy, output [31:0] rdata);
  reg [63:0] A [0:24];
  reg [63:0] Bm [0:24];
  reg [63:0] C0, C1, C2, C3, C4, R0, R1, R2, R3, R4;
  reg [1:0]  ph;            // 0: column parity, 1: theta+rho+pi, 2: chi read, 3: chi write
  reg [4:0]  i, rnd;        // lane / row counter, round
  reg [2:0]  k;             // lane within row
  reg        run;

  function [5:0] rho(input [4:0] n);
    case (n)
      0: rho=0;  1: rho=1;  2: rho=62; 3: rho=28; 4: rho=27; 5: rho=36; 6: rho=44; 7: rho=6;  8: rho=55; 9: rho=20;
      10: rho=3; 11: rho=10; 12: rho=43; 13: rho=25; 14: rho=39; 15: rho=41; 16: rho=45; 17: rho=15; 18: rho=21; 19: rho=8;
      20: rho=18; 21: rho=2; 22: rho=61; 23: rho=56; default: rho=14;
    endcase
  endfunction
  function [63:0] rc(input [4:0] n);
    case (n)
      0: rc=64'h0000000000000001; 1: rc=64'h0000000000008082; 2: rc=64'h800000000000808a; 3: rc=64'h8000000080008000;
      4: rc=64'h000000000000808b; 5: rc=64'h0000000080000001; 6: rc=64'h8000000080008081; 7: rc=64'h8000000000008009;
      8: rc=64'h000000000000008a; 9: rc=64'h0000000000000088; 10: rc=64'h0000000080008009; 11: rc=64'h000000008000000a;
      12: rc=64'h000000008000808b; 13: rc=64'h800000000000008b; 14: rc=64'h8000000000008089; 15: rc=64'h8000000000008003;
      16: rc=64'h8000000000008002; 17: rc=64'h8000000000000080; 18: rc=64'h000000000000800a; 19: rc=64'h800000008000000a;
      20: rc=64'h8000000080008081; 21: rc=64'h8000000000008080; 22: rc=64'h0000000080000001; default: rc=64'h8000000080008008;
    endcase
  endfunction
  function [2:0] mod5(input [4:0] n); mod5 = n % 5; endfunction
  function [2:0] div5(input [4:0] n); div5 = n / 5; endfunction

  // theta D for column x
  wire [2:0] x = mod5(i), y = div5(i);
  reg  [63:0] Cx_m1, Cx_p1;
  always @* begin
    case (x) 0: begin Cx_m1 = C4; Cx_p1 = C1; end 1: begin Cx_m1 = C0; Cx_p1 = C2; end
             2: begin Cx_m1 = C1; Cx_p1 = C3; end 3: begin Cx_m1 = C2; Cx_p1 = C4; end
             default: begin Cx_m1 = C3; Cx_p1 = C0; end endcase
  end
  wire [63:0] D   = Cx_m1 ^ {Cx_p1[62:0], Cx_p1[63]};
  wire [63:0] ain = A[i];
  wire [63:0] t   = ain ^ D;
  wire [5:0]  r   = rho(i);
  wire [63:0] rot = (t << r) | (t >> (7'd64 - {1'b0, r}));   // r = 0 -> (t >> 64) = 0 -> t
  wire [4:0]  bidx = y + 5 * ((2 * x + 3 * y) % 5);
  // chi on the buffered row
  reg  [63:0] cr, cr1, cr2;
  always @* begin
    case (k) 0: begin cr = R0; cr1 = R1; cr2 = R2; end 1: begin cr = R1; cr1 = R2; cr2 = R3; end
             2: begin cr = R2; cr1 = R3; cr2 = R4; end 3: begin cr = R3; cr1 = R4; cr2 = R0; end
             default: begin cr = R4; cr1 = R0; cr2 = R1; end endcase
  end
  wire [63:0] chi = cr ^ (~cr1 & cr2) ^ ((i == 0 && k == 0) ? rc(rnd) : 64'd0);
  wire [63:0] bin = Bm[5 * i + k];   // in phase 2, i = row y, k = x

  always @(posedge clk) begin
    if (rst) begin run <= 0; end
    else if (start) begin run <= 1; ph <= 0; i <= 0; k <= 0; rnd <= 0;
                          C0 <= 0; C1 <= 0; C2 <= 0; C3 <= 0; C4 <= 0; end
    else if (run) begin
      case (ph)
        2'd0: begin   // column parity
          case (x) 0: C0 <= C0 ^ ain; 1: C1 <= C1 ^ ain; 2: C2 <= C2 ^ ain; 3: C3 <= C3 ^ ain; default: C4 <= C4 ^ ain; endcase
          if (i == 24) begin i <= 0; ph <= 1; end else i <= i + 1;
        end
        2'd1: begin   // theta + rho + pi
          Bm[bidx] <= rot;
          if (i == 24) begin i <= 0; k <= 0; ph <= 2; end else i <= i + 1;
        end
        2'd2: begin   // read one row of B
          case (k) 0: R0 <= bin; 1: R1 <= bin; 2: R2 <= bin; 3: R3 <= bin; default: R4 <= bin; endcase
          if (k == 4) begin k <= 0; ph <= 3; end else k <= k + 1;
        end
        default: begin // chi + iota, write row back to A
          A[5 * i + k] <= chi;
          if (k == 4) begin
            k <= 0;
            if (i == 4) begin
              i <= 0; ph <= 0; C0 <= 0; C1 <= 0; C2 <= 0; C3 <= 0; C4 <= 0;
              if (rnd == 23) run <= 0; else rnd <= rnd + 1;
            end else begin i <= i + 1; ph <= 2; end
          end else k <= k + 1;
        end
      endcase
    end
    else if (ld) begin
      if (widx[0]) A[widx[5:1]][63:32] <= wdata; else A[widx[5:1]][31:0] <= wdata;
    end
  end
  assign busy  = run;
  assign rdata = widx[0] ? A[widx[5:1]][63:32] : A[widx[5:1]][31:0];
endmodule
