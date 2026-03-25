#include "xparameters.h"
#include "xil_printf.h"
#include "xgpio.h"
#include "puf_data.h"

#define MAX_CRPS        100
#define GPIO_IN_ID       XPAR_AXI_GPIO_1_BASEADDR  // For Reading (State)
#define GPIO_OUT_ID      XPAR_AXI_GPIO_0_BASEADDR  // For Writing (Commands)

#define MAGIC_ENROLLED_VAL 0xDEADBEEF
unsigned int enrollment_check __attribute__((section(".noinit")));
unsigned int enrolled_hash_persistent __attribute__((section(".noinit")));

// FSM states
#define STATE_IDLE      0
#define STATE_ENCRYPT   1
#define STATE_DECRYPT   2
#define STATE_REJECT    3

XGpio gpio_in, gpio_out;

// Simple hash of first N PUF responses — used for device matching
unsigned int compute_device_hash() {
    unsigned int hash = 0;
    for (int i = 0; i < 10; i++) {
        hash ^= puf_responses[i] << i;
    }
    return hash;
}

static unsigned int enrolled_hash = 0;
static int is_enrolled = 0;

int main() {

    if (enrollment_check == MAGIC_ENROLLED_VAL) {
        is_enrolled = 1;
        enrolled_hash = enrolled_hash_persistent;
    } else {
        is_enrolled = 0;
        enrolled_hash = 0;
    }
    
    //xil_printf("SYSTEM REBOOTED\r\n");
    XGpio_Initialize(&gpio_in,  GPIO_IN_ID);
    XGpio_Initialize(&gpio_out, GPIO_OUT_ID);
    XGpio_SetDataDirection(&gpio_in,  1, 0xFFFFFFFF); // input
    XGpio_SetDataDirection(&gpio_out, 1, 0x00000000); // output


    //xil_printf("PUF Security FSM ready\r\n");

    while (1) {
        // Wait for command from PC over UART
        u8 cmd = inbyte();

        if (cmd == 0xFF) {  // reset enrollment
            is_enrolled = 0;
            enrolled_hash = 0;
            enrollment_check = 0x00000000;
            enrolled_hash_persistent = 0;
            //xil_printf("ENROLLMENT CLEARED\r\n");
            outbyte(0xFF);  // ack
        }

        if (cmd == 0x01) {
            unsigned int current_puf_hash = compute_device_hash();
            
            // Read the "Claimed ID" from the PC (4 bytes)
            u8 claimed_id_bytes[4];
            for (int i = 0; i < 4; i++) claimed_id_bytes[i] = inbyte();
            unsigned int claimed_id = (claimed_id_bytes[0] << 24) | (claimed_id_bytes[1] << 16) | 
                                    (claimed_id_bytes[2] << 8)  | (claimed_id_bytes[3]);

            if (!is_enrolled) {
                // FIRST RUN: Enroll the device
                enrolled_hash = current_puf_hash;
                is_enrolled = 1;
                enrollment_check = MAGIC_ENROLLED_VAL;
                enrolled_hash_persistent = current_puf_hash;
                
                outbyte(STATE_ENCRYPT); // Tell PC: "I'm new, let's encrypt"
                // Send the signature to the PC to be stored in the file header
                outbyte((current_puf_hash >> 24) & 0xFF);
                outbyte((current_puf_hash >> 16) & 0xFF);
                outbyte((current_puf_hash >>  8) & 0xFF);
                outbyte((current_puf_hash >>  0) & 0xFF);
            } 
            else if (claimed_id == current_puf_hash) {
                // MATCH: The file belongs to THIS chip
                outbyte(STATE_DECRYPT);
            } 
            else {
                // REJECT: The file was encrypted by a different chip!
                outbyte(STATE_REJECT);
            }
        }

        // Always respond to CRP requests too
        if (cmd == 0x02) {  // CRP request
            u8 idx_bytes[4];
            for (int i = 0; i < 4; i++)
                idx_bytes[i] = inbyte();

            unsigned int idx = (idx_bytes[0] << 24) | (idx_bytes[1] << 16) | 
                       (idx_bytes[2] << 8)  | (idx_bytes[3]);
    
            unsigned int response = puf_responses[idx % MAX_CRPS];

            outbyte((response >> 24) & 0xFF);
            outbyte((response >> 16) & 0xFF);
            outbyte((response >>  8) & 0xFF);
            outbyte((response >>  0) & 0xFF);
        }
    }
}
