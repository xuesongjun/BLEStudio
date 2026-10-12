#ifndef BLE_PYTHON_DPI_H
#define BLE_PYTHON_DPI_H

#include <svdpi.h>

#ifdef __cplusplus
extern "C" {
#endif

int ble_python_init(const char* python_executable, const char* module_root,
                    const char* site_packages, const char** message);

int ble_python_check(const svOpenArrayHandle i_samples, const svOpenArrayHandle q_samples,
                     double sample_rate, int phy_mode, unsigned int access_address,
                     int channel, int whitening, unsigned int crc_init,
                     const char* expected_pdu_hex, const char* report_path,
                     int* passed, int* sync_found, int* crc_valid,
                     int* pdu_match, const char** message);

#ifdef __cplusplus
}
#endif

#endif
