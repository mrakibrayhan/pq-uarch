// Checks a Keccak unit (DUT module name passed with -DDUT=...) against Python reference vectors.
`timescale 1ns/1ps
module tb_keccak;
  parameter NT = 4;
  reg clk = 0, rst = 1, ld = 0, start = 0; reg [5:0] widx = 0; reg [31:0] wdata = 0;
  wire busy; wire [31:0] rdata;
  `DUT dut(.clk(clk), .rst(rst), .ld(ld), .widx(widx), .wdata(wdata), .start(start), .busy(busy), .rdata(rdata));
  always #5 clk = ~clk;
  reg [31:0] v [0:NT*100-1];
  integer t, w, cyc, errs = 0;
  initial begin
    $readmemh("vectors.hex", v);
    @(posedge clk); rst <= 0;
    for (t = 0; t < NT; t = t + 1) begin
      for (w = 0; w < 50; w = w + 1) begin @(negedge clk); ld = 1; widx = w; wdata = v[t*100 + w]; end
      @(negedge clk); ld = 0; start = 1; @(negedge clk); start = 0; cyc = 1;
      while (busy) begin @(negedge clk); cyc = cyc + 1; end
      for (w = 0; w < 50; w = w + 1) begin widx = w; #1; if (rdata !== v[t*100 + 50 + w]) errs = errs + 1; end
      $display("vector %0d: permutation cycles=%0d", t, cyc);
    end
    $display("KECCAK_CHECK errors=%0d", errs); $finish;
  end
endmodule
