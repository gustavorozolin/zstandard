import Cocoa
import FlutterMacOS
#if canImport(zstandard_ffi)
import zstandard_ffi
#endif

public class ZstandardMacosPlugin: NSObject, FlutterPlugin {
  public static func register(with registrar: FlutterPluginRegistrar) {
    #if canImport(zstandard_ffi)
    zstandard_ffi_retain_symbols()
    #endif
    let channel = FlutterMethodChannel(name: "plugins.flutter.io/zstandard", binaryMessenger: registrar.messenger)
    let instance = ZstandardMacosPlugin()
    registrar.addMethodCallDelegate(instance, channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "getPlatformVersion":
      result("macOS " + ProcessInfo.processInfo.operatingSystemVersionString)
    default:
      result(FlutterMethodNotImplemented)
    }
  }
}
