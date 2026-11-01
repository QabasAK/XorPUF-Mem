`timescale 1 ns / 1 ps
module xor_enc_dec #
(
    parameter integer C_S_AXIS_TDATA_WIDTH    = 32,
    parameter integer C_M_AXIS_TDATA_WIDTH    = 32,
    parameter integer C_M_AXIS_START_COUNT    = 32,
    parameter integer C_S00_AXI_DATA_WIDTH    = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH    = 4
)
(
    output wire [31:0] bram_addr,
    input  wire [31:0] bram_dout,
    output wire        bram_en,
    input wire  s_axis_aclk,
    input wire  s_axis_aresetn,
    output wire  s_axis_tready,
    input wire [C_S_AXIS_TDATA_WIDTH-1 : 0] s_axis_tdata,
    input wire [(C_S_AXIS_TDATA_WIDTH/8)-1 : 0] s_axis_tstrb,
    input wire  s_axis_tlast,
    input wire  s_axis_tvalid,
    input wire  m_axis_aclk,
    input wire  m_axis_aresetn,
    output wire  m_axis_tvalid,
    output wire [C_M_AXIS_TDATA_WIDTH-1 : 0] m_axis_tdata,
    output wire [(C_M_AXIS_TDATA_WIDTH/8)-1 : 0] m_axis_tstrb,
    output wire  m_axis_tlast,
    input wire  m_axis_tready,
    input wire  s00_axi_aclk,
    input wire  s00_axi_aresetn,
    input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_awaddr,
    input wire [2 : 0] s00_axi_awprot,
    input wire  s00_axi_awvalid,
    output wire  s00_axi_awready,
    input wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_wdata,
    input wire [(C_S00_AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb,
    input wire  s00_axi_wvalid,
    output wire  s00_axi_wready,
    output wire [1 : 0] s00_axi_bresp,
    output wire  s00_axi_bvalid,
    input wire  s00_axi_bready,
    input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_araddr,
    input wire [2 : 0] s00_axi_arprot,
    input wire  s00_axi_arvalid,
    output wire  s00_axi_arready,
    output wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_rdata,
    output wire [1 : 0] s00_axi_rresp,
    output wire  s00_axi_rvalid,
    input wire  s00_axi_rready
);

    // ── AXI-Lite register (slv_reg0[0] = reset pulse) ────────────
    reg [31:0] slv_reg0;
    reg axi_awready, axi_wready, axi_bvalid, axi_arready, axi_rvalid;
    reg [1:0] axi_bresp, axi_rresp;
    reg [31:0] axi_rdata;

    assign s00_axi_awready = axi_awready;
    assign s00_axi_wready  = axi_wready;
    assign s00_axi_bresp   = axi_bresp;
    assign s00_axi_bvalid  = axi_bvalid;
    assign s00_axi_arready = axi_arready;
    assign s00_axi_rdata   = axi_rdata;
    assign s00_axi_rresp   = axi_rresp;
    assign s00_axi_rvalid  = axi_rvalid;

    // Write logic
    always @(posedge s00_axi_aclk) begin
        if (!s00_axi_aresetn) begin
            slv_reg0    <= 0;
            axi_awready <= 0;
            axi_wready  <= 0;
            axi_bvalid  <= 0;
            axi_bresp   <= 0;
        end else begin
            // Auto-clear after one cycle so it acts as a pulse
            slv_reg0 <= 0;

            if (s00_axi_awvalid && s00_axi_wvalid) begin
                slv_reg0    <= s00_axi_wdata;
                axi_awready <= 1;
                axi_wready  <= 1;
                axi_bvalid  <= 1;
                axi_bresp   <= 2'b00;
            end else begin
                axi_awready <= 0;
                axi_wready  <= 0;
                if (axi_bvalid && s00_axi_bready)
                    axi_bvalid <= 0;
            end
        end
    end

    // Read logic (just return slv_reg0)
    always @(posedge s00_axi_aclk) begin
        if (!s00_axi_aresetn) begin
            axi_arready <= 0;
            axi_rvalid  <= 0;
            axi_rdata   <= 0;
            axi_rresp   <= 0;
        end else begin
            if (s00_axi_arvalid) begin
                axi_arready <= 1;
                axi_rdata   <= slv_reg0;
                axi_rvalid  <= 1;
                axi_rresp   <= 2'b00;
            end else begin
                axi_arready <= 0;
                if (axi_rvalid && s00_axi_rready)
                    axi_rvalid <= 0;
            end
        end
    end

    // ── XOR Engine ────────────────────────────────────────────────
    reg [9:0] byte_cnt;
    wire [7:0] puf_byte;
    
    reg slv_reg0_sync1, slv_reg0_sync2;
    always @(posedge s_axis_aclk) begin
        slv_reg0_sync1 <= slv_reg0[0];
        slv_reg0_sync2 <= slv_reg0_sync1;
    end
    
    
    assign bram_en   = 1'b1;
    assign bram_addr = ((byte_cnt >> 2) % 100) * 4;
    assign puf_byte  = bram_dout[(8*(3-byte_cnt[1:0])) +: 8];

    always @(posedge s_axis_aclk) begin
        if (!s_axis_aresetn || slv_reg0[0]) begin
            byte_cnt <= 0;
        end else if (s_axis_tvalid && s_axis_tready) begin
            byte_cnt <= byte_cnt + 1;
        end
    end

    assign m_axis_tdata  = s_axis_tdata ^ {24'b0, puf_byte};
    assign m_axis_tvalid = s_axis_tvalid;
    assign m_axis_tlast  = s_axis_tlast;
    assign s_axis_tready = m_axis_tready;
    assign m_axis_tstrb  = s_axis_tstrb;

endmodule