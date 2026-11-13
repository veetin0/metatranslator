import Foundation

/// Reads DAT error text for the go/no-go. The docs say some capabilities are gated per user
/// on Meta's servers and a request "may be declined at runtime, returning
/// `DeviceSessionError.CAPABILITY_DENIED`" (docs: develop/dat/version-dependencies). The Swift
/// enum in 1.0.1 has no such case (`noEligibleDevice`, `capabilityAlreadyActive`,
/// `capabilityNotFound`, `unexpectedError(description:)`, ...), so a denial can arrive under
/// another name. Every DAT error is logged verbatim, and this flags the ones that look like
/// a denial so the lead reports them to Meta at once.
enum DatErrorTriage {
  enum Kind: Equatable {
    case capabilityDenied
    case noDevice
    case updateRequired
    case thermalOrPower
    case other
  }

  static func classify(_ text: String) -> Kind {
    let t = text.lowercased()
    if t.contains("capability_denied") || t.contains("capabilitydenied")
      || (t.contains("capabilit") && t.contains("denied"))
    {
      return .capabilityDenied
    }
    if t.contains("noeligibledevice") || t.contains("no eligible device")
      || t.contains("nodevicewithconnection")
    {
      return .noDevice
    }
    if t.contains("updaterequired") || t.contains("update required") { return .updateRequired }
    if t.contains("thermal") || t.contains("peakpower") || t.contains("battery") {
      return .thermalOrPower
    }
    return .other
  }

  static func describe(_ error: Error) -> String {
    let named = String(describing: error)
    let localized = error.localizedDescription
    return named == localized ? named : "\(named) (\(localized))"
  }
}
