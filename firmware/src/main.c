#include "xparameters.h"
#include "xil_printf.h"
#include "xgpio.h"
#include "xil_io.h"
#include "puf_data.h"
#include <xmem_config.h>

#define XOR_ENGINE_BASE  XPAR_XOR_ENC_DEC_0_BASEADDR      // 0x44a00000
#define PUF_BRAM_BASE    XPAR_AXI_BRAM_CTRL_0_BASEADDR    // 0xc0000000
#define GPIO_IN_ID       XPAR_AXI_GPIO_1_BASEADDR         // 0x40010000

#define STATE_IDLE      0
#define STATE_ENCRYPT   1
#define STATE_DECRYPT   2
#define STATE_REJECT    3
#define MAX_CRPS        100
#define MAGIC_ENROLLED_VAL 0xDEADBEEF

unsigned int enrollment_check       __attribute__((section(".noinit")));
unsigned int enrolled_hash_persistent __attribute__((section(".noinit")));

XGpio gpio_in;

// ── Load PUF responses into BRAM at boot ─────────────────────────
void load_puf_to_bram() {
    for (int i = 0; i < MAX_CRPS; i++) {
        Xil_Out32(PUF_BRAM_BASE + (i * 4), puf_responses[i]);
    }
    //u32 check0 = Xil_In32(PUF_BRAM_BASE + 0);
    //u32 check99 = Xil_In32(PUF_BRAM_BASE + (99 * 4));
    // Expected: check0 = 0x045D9F3B, check99 = 0xB492330C
    //xil_printf("BRAM[0]  = 0x%08X\r\n", check0);
    //xil_printf("BRAM[99] = 0x%08X\r\n", check99);
}

// ── Hash (same as before) ─────────────────────────────────────────
unsigned int compute_device_hash() {
    unsigned int hash = 0;
    for (int i = 0; i < 10; i++) {
        hash ^= puf_responses[i] << i;
    }
    return hash;
}

// 2. Restore enrollment state
static unsigned int enrolled_hash = 0;
static int is_enrolled = 0;
    
int main() {
    // 1. Load PUF data into BRAM FIRST before anything else
    load_puf_to_bram();

    if (enrollment_check == MAGIC_ENROLLED_VAL) {
        is_enrolled = 1;
        enrolled_hash = enrolled_hash_persistent;
    }

    // 3. Init GPIO
    XGpio_Initialize(&gpio_in, GPIO_IN_ID);
    XGpio_SetDataDirection(&gpio_in, 1, 0xFFFFFFFF);

    while (1) {
        u8 cmd = inbyte();

        // ── Reset enrollment ──────────────────────────────────────
        if (cmd == 0xFF) {
            is_enrolled = 0;
            enrolled_hash = 0;
            enrollment_check = 0x00000000;
            enrolled_hash_persistent = 0;
            outbyte(0xFF);
        }

        // ── Authentication ────────────────────────────────────────
        if (cmd == 0x01) {
            unsigned int current_puf_hash = compute_device_hash();

            u8 claimed_id_bytes[4];
            for (int i = 0; i < 4; i++) claimed_id_bytes[i] = inbyte();
            unsigned int claimed_id = (claimed_id_bytes[0] << 24) |
                                      (claimed_id_bytes[1] << 16) |
                                      (claimed_id_bytes[2] <<  8) |
                                      (claimed_id_bytes[3]);

            if (!is_enrolled) {
                enrolled_hash = current_puf_hash;
                is_enrolled = 1;
                enrollment_check = MAGIC_ENROLLED_VAL;
                enrolled_hash_persistent = current_puf_hash;

                outbyte(STATE_ENCRYPT);
                outbyte((current_puf_hash >> 24) & 0xFF);
                outbyte((current_puf_hash >> 16) & 0xFF);
                outbyte((current_puf_hash >>  8) & 0xFF);
                outbyte((current_puf_hash >>  0) & 0xFF);
            }
            else if (claimed_id == current_puf_hash) {
                outbyte(STATE_DECRYPT);
            }
            else {
                outbyte(STATE_REJECT);
            }
        }

        // ── Hardware XOR Encrypt/Decrypt ──────────────────────────
        if (cmd == 0x03) {

            Xil_Out32(XOR_ENGINE_BASE + 0, 0x00000001);
            for(volatile int d = 0; d < 100000; d++);
            Xil_Out32(XOR_ENGINE_BASE + 0, 0x00000000);
            for(volatile int d = 0; d < 100000; d++);

            
            u32 file_size = 0;
            file_size |= ((u32)inbyte() << 24);
            file_size |= ((u32)inbyte() << 16);
            file_size |= ((u32)inbyte() <<  8);
            file_size |= ((u32)inbyte());

            u8 dummy = 0x00;
            putfsl(dummy, 0);
            u8 dummy_out;
            getfsl(dummy_out, 0);
            
            for (u32 i = 0; i < file_size; i++) {
                u8 raw_byte = inbyte();
                putfsl(raw_byte, 0);   // push to XOR engine S_AXIS
                u8 processed_byte;
                getfsl(processed_byte, 0);  // pull from XOR engine M_AXIS
                outbyte(processed_byte);    // send back to PC
            }
        }
    }
}