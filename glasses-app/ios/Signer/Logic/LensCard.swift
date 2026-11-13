import Foundation

/// How a caption is drawn, from its tier (DESIGN.md, Lens palette):
/// confirmed = white, unsure = amber with a "?", none = dim.
enum LensTone: Equatable {
  case confirmed
  case unsure
  case dim

  init(tier: CaptionTier) {
    switch tier {
    case .confirmed: self = .confirmed
    case .unsure: self = .unsure
    case .none: self = .dim
    }
  }

  /// The DESIGN.md colour. Used on the phone screen preview and the Web App.
  var hex: String {
    switch self {
    case .confirmed: return "#FFFFFF"
    case .unsure: return "#FFB020"
    case .dim: return "#9AA4B2"
    }
  }

  /// DAT Display `Text` only offers `TextColor.primary` and `.secondary` (MWDATDisplay 1.0.1),
  /// no hex. So on the glasses the tier is carried by this slot plus the "?" prefix, and amber
  /// exists only on the phone preview. Reported to the integrator as a DESIGN.md gap.
  enum Slot: Equatable { case primary, secondary }

  var datSlot: Slot {
    switch self {
    case .confirmed: return .primary
    case .unsure, .dim: return .secondary
    }
  }

  /// "?" marks an unsure caption in text, since amber is not available on the DAT card.
  var textPrefix: String { self == .unsure ? "? " : "" }
}

/// Everything one DAT Display card (or its phone preview) shows. Equatable so the throttle
/// can drop a send that would not change the screen.
struct LensCard: Equatable {
  var stateLine: String
  /// Caption lines, at most `CaptionWrapper.maxLines`, each at most `maxCharsPerLine`.
  var lines: [String]
  var tone: LensTone
  /// Footer readout, e.g. "17/19 confirmed".
  var footer: String?

  static let hello = LensCard(
    stateLine: LensState.on.label, lines: ["Hello"], tone: .confirmed, footer: "Signer spike")

  /// Card for a caption event. `none` tier shows the dim "Didn't catch that" text from the core.
  static func caption(_ c: CaptionEvent, state: LensState = .on, stats: StatsEvent? = nil) -> LensCard {
    let tone = LensTone(tier: c.tier)
    let text = tone.textPrefix + c.text
    return LensCard(
      stateLine: state.label,
      lines: CaptionWrapper.lines(text),
      tone: tone,
      footer: stats.map { "\($0.confirmed)/\($0.total) confirmed" })
  }

  /// Card with no caption, only the state line (connecting, core down, ...).
  static func state(_ state: LensState, stats: StatsEvent? = nil) -> LensCard {
    LensCard(
      stateLine: state.label, lines: [], tone: .dim,
      footer: stats.map { "\($0.confirmed)/\($0.total) confirmed" })
  }
}

/// Word wrap for the lens: at most 2 lines of about 24 characters (CONTRACTS section 7,
/// DESIGN.md). When the text needs more, the oldest line drops (we keep the last lines).
enum CaptionWrapper {
  static let maxCharsPerLine = 24
  static let maxLines = 2

  static func lines(
    _ text: String, maxChars: Int = maxCharsPerLine, maxLines: Int = maxLines
  ) -> [String] {
    var out: [String] = []
    var current = ""
    for rawWord in text.split(whereSeparator: { $0.isWhitespace }) {
      var word = String(rawWord)
      // A single word longer than a line is hard-split.
      while word.count > maxChars {
        if !current.isEmpty { out.append(current); current = "" }
        out.append(String(word.prefix(maxChars)))
        word = String(word.dropFirst(maxChars))
      }
      if current.isEmpty {
        current = word
      } else if current.count + 1 + word.count <= maxChars {
        current += " " + word
      } else {
        out.append(current)
        current = word
      }
    }
    if !current.isEmpty { out.append(current) }
    return Array(out.suffix(maxLines))
  }
}

/// Which captions are spoken: only `speak: true` (the core sets it for `confirmed` only),
/// and never the same caption id twice.
struct SpeechPolicy {
  private(set) var spokenIds: Set<String> = []

  mutating func shouldSpeak(_ c: CaptionEvent) -> Bool {
    guard c.speak, !c.text.isEmpty else { return false }
    return spokenIds.insert(c.id).inserted
  }
}
