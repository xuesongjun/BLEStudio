// 在仿真进程内嵌入 CPython；解释器和缓存 callable 保持到进程退出。
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "ble_python_dpi.h"

#include <cstdio>
#include <exception>
#include <fstream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

#if PY_VERSION_HEX < 0x030A0000
#error "The DPI bridge requires Python 3.10 or newer"
#endif

namespace {
struct PyDeleter {
    void operator()(PyObject* value) const { Py_XDECREF(value); }
};
using PyRef = std::unique_ptr<PyObject, PyDeleter>;

struct GilGuard {
    PyGILState_STATE state;
    GilGuard() : state(PyGILState_Ensure()) {}
    ~GilGuard() { PyGILState_Release(state); }
};

std::mutex bridge_mutex;
PyObject* checker = nullptr;
std::string initialized_environment;
thread_local std::string last_message;

void set_message(const std::string& text, const char** output) {
    // SV 会复制 output string；保持底层存储有效到本线程下一次调用。
    last_message = text;
    if (output) {
        *output = last_message.c_str();
    }
}

std::string python_error() {
    PyObject *type = nullptr, *value = nullptr, *trace = nullptr;
    PyErr_Fetch(&type, &value, &trace);
    PyErr_NormalizeException(&type, &value, &trace);
    PyRef type_ref(type), value_ref(value), trace_ref(trace);
    PyRef module(PyImport_ImportModule("traceback"));
    PyRef formatter(module ? PyObject_GetAttrString(module.get(), "format_exception") : nullptr);
    PyRef lines(formatter ? PyObject_CallFunctionObjArgs(
        formatter.get(), type ? type : Py_None, value ? value : Py_None,
        trace ? trace : Py_None, nullptr) : nullptr);
    PyRef separator(PyUnicode_FromString(""));
    PyRef text(lines && separator ? PyUnicode_Join(separator.get(), lines.get()) : nullptr);
    if (text) {
        const char* utf8 = PyUnicode_AsUTF8(text.get());
        if (utf8) {
            return utf8;
        }
    }
    PyErr_Clear();
    PyRef fallback(value ? PyObject_Str(value) : nullptr);
    const char* utf8 = fallback ? PyUnicode_AsUTF8(fallback.get()) : nullptr;
    std::string result = utf8 ? utf8 : "Unknown Python exception";
    PyErr_Clear();
    return result;
}

void require_python(bool condition) {
    if (!condition) {
        throw std::runtime_error(python_error());
    }
}

void prepend_path(const char* path) {
    if (!path || !*path) {
        return;
    }
    PyObject* sys_path = PySys_GetObject("path");  // borrowed
    PyRef entry(PyUnicode_FromString(path));
    require_python(sys_path && entry && PyList_Insert(sys_path, 0, entry.get()) == 0);
}

PyRef real_array(const svOpenArrayHandle handle) {
    if (!handle || svDimensions(handle) != 1) {
        throw std::runtime_error("DPI I/Q must be one-dimensional open arrays");
    }
    const int size = svSize(handle, 1);
    const int left = svLeft(handle, 1);
    const int step = svRight(handle, 1) >= left ? 1 : -1;
    PyRef result(PyList_New(size));
    require_python(static_cast<bool>(result));
    for (int index = 0; index < size; ++index) {
        const auto* element = static_cast<const double*>(
            svGetArrElemPtr1(handle, left + index * step));
        if (!element) {
            throw std::runtime_error("DPI cannot access a real array element");
        }
        PyObject* value = PyFloat_FromDouble(*element);
        require_python(value != nullptr);
        PyList_SET_ITEM(result.get(), index, value);  // steals reference
    }
    return result;
}

int result_bool(PyObject* result, const char* name) {
    PyObject* value = PyDict_GetItemString(result, name);  // borrowed
    if (!value || !PyBool_Check(value)) {
        throw std::runtime_error(std::string("Invalid checker boolean: ") + name);
    }
    return value == Py_True ? 1 : 0;
}

std::string result_text(PyObject* result, const char* name) {
    PyObject* value = PyDict_GetItemString(result, name);  // borrowed
    if (!value || !PyUnicode_Check(value)) {
        throw std::runtime_error(std::string("Invalid checker string: ") + name);
    }
    const char* text = PyUnicode_AsUTF8(value);
    require_python(text != nullptr);
    return text;
}
}  // namespace

extern "C" int ble_python_init(
    const char* python_executable, const char* module_root,
    const char* site_packages, const char** message
) {
    std::lock_guard<std::mutex> lock(bridge_mutex);
    try {
        if (!python_executable || !*python_executable || !module_root || !*module_root) {
            throw std::runtime_error("BLE_PYTHON and BLE_MODULE_ROOT must be specified");
        }
        if (!std::ifstream(std::string(module_root) + "/ble_studio/tx_checker.py").good()) {
            throw std::runtime_error("BLE_MODULE_ROOT does not contain ble_studio/tx_checker.py");
        }
        const std::string environment = std::string(python_executable) + "\n" + module_root
            + "\n" + (site_packages ? site_packages : "");
        if (checker) {
            if (environment != initialized_environment) {
                throw std::runtime_error("Python bridge was initialized with different paths");
            }
            set_message("Python checker already initialized", message);
            return 0;
        }
        if (!Py_IsInitialized()) {
            PyConfig config;
            PyConfig_InitPythonConfig(&config);
            config.install_signal_handlers = 0;
            config.parse_argv = 0;
            config.user_site_directory = 0;
            PyStatus status = PyConfig_SetBytesString(&config, &config.program_name, python_executable);
            if (!PyStatus_Exception(status)) {
                status = PyConfig_SetBytesString(&config, &config.executable, python_executable);
            }
            if (!PyStatus_Exception(status)) {
                status = Py_InitializeFromConfig(&config);
            }
            const bool failed = PyStatus_Exception(status);
            const std::string detail = failed && status.err_msg ? status.err_msg : "Python initialization failed";
            PyConfig_Clear(&config);
            if (failed) {
                throw std::runtime_error(detail);
            }
            // 新建解释器初始化时持有 GIL，释放后每次调用由 GilGuard 管理。
            PyEval_SaveThread();
        }
        GilGuard gil;
        prepend_path(site_packages);
        prepend_path(module_root);
        PyRef module(PyImport_ImportModule("ble_studio.tx_checker"));
        require_python(static_cast<bool>(module));
        PyRef function(PyObject_GetAttrString(module.get(), "check_tx_packet_dpi"));
        require_python(static_cast<bool>(function));
        if (!PyCallable_Check(function.get())) {
            throw std::runtime_error("check_tx_packet_dpi is not callable");
        }
        checker = function.release();
        initialized_environment = environment;
        set_message(std::string("Python checker initialized: ") + Py_GetVersion(), message);
        return 0;
    } catch (const std::exception& error) {
        set_message(std::string("BRIDGE_INIT_ERROR: ") + error.what(), message);
        std::fprintf(stderr, "[BLE-PYTHON] %s\n", last_message.c_str());
        return -1;
    }
}

extern "C" int ble_python_check(
    const svOpenArrayHandle i_samples, const svOpenArrayHandle q_samples,
    double sample_rate, int phy_mode, unsigned int access_address,
    int channel, int whitening, unsigned int crc_init,
    const char* expected_pdu_hex, const char* report_path,
    int* passed, int* sync_found, int* crc_valid, int* pdu_match, const char** message
) {
    std::lock_guard<std::mutex> lock(bridge_mutex);
    if (passed) *passed = 0;
    if (sync_found) *sync_found = 0;
    if (crc_valid) *crc_valid = 0;
    if (pdu_match) *pdu_match = 0;
    try {
        if (!checker || !passed || !sync_found || !crc_valid || !pdu_match) {
            throw std::runtime_error("Bridge is not initialized or output arguments are invalid");
        }
        GilGuard gil;
        PyRef i_values = real_array(i_samples);
        PyRef q_values = real_array(q_samples);
        PyRef arguments(Py_BuildValue(
            "(OOdiIiiIss)", i_values.get(), q_values.get(), sample_rate,
            phy_mode, access_address, channel, whitening, crc_init,
            expected_pdu_hex ? expected_pdu_hex : "", report_path ? report_path : ""));
        require_python(static_cast<bool>(arguments));
        PyRef result(PyObject_CallObject(checker, arguments.get()));
        require_python(static_cast<bool>(result));
        if (!PyDict_Check(result.get())) {
            throw std::runtime_error("Checker must return a result dictionary");
        }
        const int pass_value = result_bool(result.get(), "passed");
        const int sync_value = result_bool(result.get(), "sync_found");
        const int crc_value = result_bool(result.get(), "crc_valid");
        const int match_value = result_bool(result.get(), "pdu_match");
        std::string reason = result_text(result.get(), "failure_reason");
        const std::string detail = (pass_value ? "PASS" : reason)
            + " received_pdu=" + result_text(result.get(), "received_pdu_hex")
            + " expected_pdu=" + result_text(result.get(), "expected_pdu_hex");
        *passed = pass_value;
        *sync_found = sync_value;
        *crc_valid = crc_value;
        *pdu_match = match_value;
        set_message(detail, message);
        return 0;
    } catch (const std::exception& error) {
        set_message(std::string("BRIDGE_CHECK_ERROR: ") + error.what(), message);
        std::fprintf(stderr, "[BLE-PYTHON] %s\n", last_message.c_str());
        return -1;
    }
}
