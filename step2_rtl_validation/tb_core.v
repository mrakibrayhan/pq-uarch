// Testbench: runs a program on the author's RV32IM 5-stage pipelined core (RTL, unmodified)
// and reports cycles from run-enable to 'halted', retired instructions and a0.
`timescale 1ns/1ps
module tb_core;
  parameter MUL_FAST = 0;
  parameter IMEM_AW = 14;          // 64 KB instruction ROM
  parameter DMEM_AW = 15;          // 128 KB data RAM
  parameter MAXCYC  = 400000000;
  reg clk = 0, rst = 1, en = 0;
  always #5 clk = ~clk;
  wire halted, fault, pipe_empty, illegal, ev_retire, ev_stall, ev_mstall, ev_redirect;
  wire [31:0] stop_pc, x10, s_rf, s_dm, pcf, pcd, insd, pce; wire [3:0] dv; wire be, tk;
  cpu_top_pipe_riscv #(.MUL_FAST(MUL_FAST), .ENABLE_M(1), .IMEM_AW(IMEM_AW), .DMEM_AW(DMEM_AW)) dut (
    .clk(clk), .rst(rst), .en(en), .drain(1'b0), .snap_override(1'b0), .snap_idx(6'd0),
    .snap_rf_data(s_rf), .snap_dm_data(s_dm), .halted(halted), .pipe_empty(pipe_empty),
    .illegal_flag(illegal), .fault(fault), .stop_pc(stop_pc), .ev_retire(ev_retire), .ev_stall(ev_stall),
    .ev_mstall(ev_mstall), .ev_redirect(ev_redirect), .debug_pc_f(pcf), .debug_pc_d(pcd), .debug_instr_d(insd),
    .debug_pc_e(pce), .debug_valid(dv), .debug_branch_ex(be), .debug_taken(tk), .debug_x10(x10));
  reg [63:0] cyc = 0, ret = 0, lus = 0, mst = 0, red = 0;
  integer i;
  initial begin
    for (i = 0; i < 40; i = i + 1) @(posedge clk);
    rst = 0; @(posedge clk); en = 1;
    while (!halted && !fault && cyc < MAXCYC) begin
      @(posedge clk); cyc = cyc + 1;
      if (ev_retire) ret = ret + 1; if (ev_stall) lus = lus + 1; if (ev_mstall) mst = mst + 1; if (ev_redirect) red = red + 1;
    end
    $display("RESULT cycles=%0d retired=%0d a0=%0d halted=%0d fault=%0d stop_pc=%0h loaduse=%0d mstall=%0d redirect=%0d",
             cyc, ret, x10, halted, fault, stop_pc, lus, mst, red);
    $finish;
  end
endmodule
