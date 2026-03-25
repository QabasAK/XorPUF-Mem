`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/22/2026 02:25:27 AM
// Design Name: 
// Module Name: usb_security_fsm
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module usb_security_fsm (
    input  wire clk,
    input  wire rst,
    input  wire usb_inserted,    // signal from PC via UART
    input  wire device_match,    // 1 if PUF matches stored hash
    output reg  [1:0] state_out, // 0=IDLE, 1=ENCRYPT, 2=DECRYPT, 3=REJECT
    output reg  action_valid     // pulse when action is ready
);

    // State encoding
    localparam IDLE     = 2'b00;
    localparam ENCRYPT  = 2'b01;
    localparam DECRYPT  = 2'b10;
    localparam REJECT   = 2'b11;

    reg [1:0] state, next_state;
    reg device_enrolled;  // has a device been enrolled yet?

    // State register
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            state          <= IDLE;
            device_enrolled <= 0;
            action_valid   <= 0;
        end else begin
            state <= next_state;
            // Mark device as enrolled after first encryption
            if (state == ENCRYPT)
                device_enrolled <= 1;
            // Pulse action_valid for one cycle on transition
            action_valid <= (next_state != IDLE && state == IDLE);
        end
    end

    // Next state logic
    always @(*) begin
        case (state)
            IDLE: begin
                if (usb_inserted) begin
                    if (!device_enrolled)
                        next_state = ENCRYPT;   // first time = encrypt
                    else if (device_match)
                        next_state = DECRYPT;   // same device = decrypt
                    else
                        next_state = REJECT;    // different device = reject
                end else
                    next_state = IDLE;
            end
            ENCRYPT:  next_state = IDLE;  // return to idle after action
            DECRYPT:  next_state = IDLE;
            REJECT:   next_state = IDLE;
            default:  next_state = IDLE;
        endcase
    end

    // Output
    always @(posedge clk) begin
        state_out <= state;
    end

endmodule
