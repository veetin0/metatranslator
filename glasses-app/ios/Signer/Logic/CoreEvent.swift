import Foundation

/// Confidence tier (CONTRACTS section 4, DECISION.md).
enum CaptionTier: String, Codable, Equatable {
  case confirmed
  case unsure
  case none
}

/// Lens state (CONTRACTS section 4). `core_down` is produced by clients, never by the core.
enum LensState: String, Codable, Equatable {
  case off
  case connecting
  case on
  case paused
  case glassesOff = "glasses_off"
  case permissionDenied = "permission_denied"
  case coreDown = "core_down"

  /// State line for the lens and the phone screen (icon + word, never colour alone).
  var label: String {
    switch self {
    case .off: return "Signer off"
    case .connecting: return "Connecting..."
    case .on: return "Signer ON"
    case .paused: return "Paused"
    case .glassesOff: return "Glasses off"
    case .permissionDenied: return "Permission denied"
    case .coreDown: return "Core down"
    }
  }
}

enum LinkQuality: String, Codable, Equatable {
  case ok
  case slow
}

struct CaptionAlternative: Codable, Equatable {
  var text: String
  var gloss: [String]
  var confidence: Double
}

struct CaptionEvent: Codable, Equatable {
  var id: String
  var text: String
  var gloss: [String]
  var tier: CaptionTier
  var confidence: Double
  var alternatives: [CaptionAlternative]
  var question: Bool
  var mode: String
  var speak: Bool
  var ts: Int64
}

struct StateEvent: Codable, Equatable {
  var state: LensState
  var link: LinkQuality
  var ts: Int64
}

struct PartialEvent: Codable, Equatable {
  var gloss: String
  var confidence: Double
  var ts: Int64
}

struct ReplyEvent: Codable, Equatable {
  var text: String
  var source: String
  var ts: Int64
}

struct StatsEvent: Codable, Equatable {
  var confirmed: Int
  var total: Int
}

/// One message from the core. `/ws/events` carries everything but `.ack`; `/ws/frames`
/// carries only `.ack` (text `{"type":"ack","seq":n}` every 30 frames).
enum CoreEvent: Equatable {
  case state(StateEvent)
  case partial(PartialEvent)
  case caption(CaptionEvent)
  case retract(id: String)
  case reply(ReplyEvent)
  case stats(StatsEvent)
  case ack(seq: Int)
  /// A well-formed object with a `type` this build does not know. Kept, not an error, so a
  /// newer core never breaks an older app.
  case unknown(type: String)

  enum DecodeError: Error, Equatable {
    case notJSONObject
    case missingType
    case malformed(type: String, reason: String)
  }

  static func decode(line: String) throws -> CoreEvent {
    try decode(data: Data(line.utf8))
  }

  static func decode(data: Data) throws -> CoreEvent {
    guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw DecodeError.notJSONObject
    }
    guard let type = obj["type"] as? String else { throw DecodeError.missingType }
    let decoder = JSONDecoder()
    do {
      switch type {
      case "state": return .state(try decoder.decode(StateEvent.self, from: data))
      case "partial": return .partial(try decoder.decode(PartialEvent.self, from: data))
      case "caption": return .caption(try decoder.decode(CaptionEvent.self, from: data))
      case "reply": return .reply(try decoder.decode(ReplyEvent.self, from: data))
      case "stats": return .stats(try decoder.decode(StatsEvent.self, from: data))
      case "retract":
        guard let id = obj["id"] as? String else {
          throw DecodeError.malformed(type: type, reason: "missing id")
        }
        return .retract(id: id)
      case "ack":
        guard let seq = obj["seq"] as? Int else {
          throw DecodeError.malformed(type: type, reason: "missing seq")
        }
        return .ack(seq: seq)
      default:
        return .unknown(type: type)
      }
    } catch let error as DecodeError {
      throw error
    } catch {
      throw DecodeError.malformed(type: type, reason: String(describing: error))
    }
  }
}

/// Client to core messages (CONTRACTS section 4). The spike only sends `hello`.
enum ClientMessage {
  enum Client: String { case app, card, hud }
  enum Verdict: String { case right, wrong, veto }

  case hello(Client)
  case feedback(captionId: String, verdict: Verdict)
  case reply(text: String, source: String)
  /// App to core state (flag-gated, see `AppFlags.sendStateToCore`).
  case appState(StateMessage)

  var jsonString: String {
    switch self {
    case .hello(let c): return "{\"type\":\"hello\",\"client\":\"\(c.rawValue)\"}"
    case .feedback(let id, let v):
      return "{\"type\":\"feedback\",\"caption_id\":\(Self.quote(id)),\"verdict\":\"\(v.rawValue)\"}"
    case .appState(let m): return m.jsonString
    case .reply(let text, let source):
      return "{\"type\":\"reply\",\"text\":\(Self.quote(text)),\"source\":\(Self.quote(source))}"
    }
  }

  private static func quote(_ s: String) -> String {
    guard
      let data = try? JSONSerialization.data(withJSONObject: [s], options: []),
      let str = String(data: data, encoding: .utf8)
    else { return "\"\"" }
    // `["text"]` -> `"text"`
    return String(str.dropFirst().dropLast())
  }
}
