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

    // Write logic (s00_axi_aclk domain)
    always @(posedge s00_axi_aclk) begin
        if (!s00_axi_aresetn) begin
            slv_reg0    <= 0;
            axi_awready <= 0;
            axi_wready  <= 0;
            axi_bvalid  <= 0;
            axi_bresp   <= 0;
        end else begin
            slv_reg0 <= slv_reg0;   // default: keep value
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

    // Read logic (s00_axi_aclk domain)
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

    // ── Synchronize slv_reg0 to s_axis_aclk ─────────────────────
    reg [31:0] slv_reg0_sync1, slv_reg0_sync2;
    always @(posedge s_axis_aclk) begin
        slv_reg0_sync1 <= slv_reg0;
        slv_reg0_sync2 <= slv_reg0_sync1;
    end

    // ── LFSR and multi-layer XOR engine (s_axis_aclk domain) ─────
    localparam IDLE    = 2'd0;
    localparam LAYER0  = 2'd1;
    localparam LAYER1  = 2'd2;

    reg [31:0] lfsr;               // current LFSR state
    reg [31:0] seed;               // captured seed (bits 31:1 of slv_reg0)
    reg [ 1:0] state;              // FSM state
    reg [ 1:0] byte_index;         // selects which byte of the BRAM word (0..3)
    reg [ 7:0] input_byte;         // latched input byte
    reg [ 7:0] xor_acc;            // accumulated XOR for current byte
    reg        out_valid;           // output valid flag
    reg        out_last;            // output last flag

    wire       start_pulse;         // rising edge of synchronized start bit
    wire [31:0] lfsr_next;          // next LFSR state (Fibonacci)
    wire [31:0] lfsr_feedback;      // feedback for polynomial

    // Edge detection on synchronized start bit
    reg start_bit_prev;
    always @(posedge s_axis_aclk) begin
        start_bit_prev <= slv_reg0_sync2[0];
    end
    assign start_pulse = slv_reg0_sync2[0] & ~start_bit_prev;

    // Feedback polynomial: x^32 + x^23 + x^17 + x^16 + x^14 + x^10 + x^8 + x^7 + x^6 + x^5 + x^3 + 1
    assign lfsr_feedback = lfsr[31] ^ lfsr[22] ^ lfsr[16] ^ lfsr[15] ^ lfsr[13] ^
                           lfsr[9]  ^ lfsr[7]  ^ lfsr[6]  ^ lfsr[5]  ^ lfsr[4]  ^ lfsr[2];
    assign lfsr_next = {lfsr[30:0], lfsr_feedback};

    // BRAM address: use lfsr modulo 100 to stay within the 100-word table.
    // Byte index (0..3) selects the byte inside the 32-bit word.
    assign bram_en   = 1'b1;
    assign bram_addr = ((lfsr % 100) * 4);   // word address

    // Byte from BRAM based on current byte_index (0..3).
    wire [7:0] puf_byte = bram_dout[8*(3 - byte_index) +: 8];

    // State machine and data path
    always @(posedge s_axis_aclk or negedge s_axis_aresetn) begin
        if (!s_axis_aresetn) begin
            state       <= IDLE;
            lfsr        <= 32'h0;
            seed        <= 32'h0;
            byte_index  <= 2'd0;
            input_byte  <= 8'h0;
            xor_acc     <= 8'h0;
            out_valid   <= 1'b0;
            out_last    <= 1'b0;
        end else begin
            // Default assignments
            out_valid <= 1'b0;   // output only pulses when ready

            case (state)
                IDLE: begin
                    // Wait for start pulse, capture seed
                    if (start_pulse) begin
                        seed       <= {slv_reg0_sync2[31:1], 1'b0};  // seed from bits 31:1
                        lfsr       <= {slv_reg0_sync2[31:1], 1'b0};
                        byte_index <= 2'd0;
                        state      <= LAYER0;
                    end
                end

                LAYER0: begin
                    // Wait for valid input data
                    if (s_axis_tvalid && s_axis_tready) begin
                        input_byte <= s_axis_tdata[7:0];    // capture byte
                        xor_acc    <= s_axis_tdata[7:0] ^ puf_byte;   // first layer
                        lfsr       <= lfsr_next;            // advance LFSR
                        state      <= LAYER1;
                    end
                end

                LAYER1: begin
                    // Apply second layer
                    xor_acc <= xor_acc ^ puf_byte;
                    // Advance LFSR again (for next byte)
                    lfsr    <= lfsr_next;
                    // Prepare output
                    out_valid <= 1'b1;
                    out_last  <= s_axis_tlast;   // propagate last flag
                    // Next: either next byte or finish
                    if (s_axis_tlast) begin
                        // End of stream: go back to IDLE
                        state <= IDLE;
                    end else begin
                        // Prepare for next byte: increment byte_index and stay in LAYER0
                        byte_index <= byte_index + 2'd1;
                        state      <= LAYER0;
                    end
                end
            endcase
        end
    end

    // Output AXI-Stream signals
    assign m_axis_tdata  = {24'h0, xor_acc};
    assign m_axis_tvalid = out_valid;
    assign m_axis_tlast  = out_last;
    assign m_axis_tstrb  = 4'b1111;   // all bytes valid (or you can derive from input)
    assign s_axis_tready = (state == LAYER0) && !(state == IDLE);   // ready when waiting for first layer

endmodule