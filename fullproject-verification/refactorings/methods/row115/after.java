  public static Duration parseDuration(String text) {
    ValidationUtils.checkArgument(!StringUtils.isNullOrEmpty(text));

    final String trimmed = text.trim();
    ValidationUtils.checkArgument(!trimmed.isEmpty(), "argument is an empty- or whitespace-only string");

    final int len = trimmed.length();
    int pos = 0;

    while (pos < len) {
      char current = trimmed.charAt(pos);
      if (current < '0' || current > '9') {
        break;
      }
      pos++;
    }

    final String number = trimmed.substring(0, pos);
    final String unitLabel = trimmed.substring(pos).trim().toLowerCase(Locale.US);

    if (number.isEmpty()) {
      throw new NumberFormatException("text does not start with a number");
    }

    final long value;
    try {
      value = Long.parseLong(number); // this throws a NumberFormatException on overflow
    } catch (NumberFormatException e) {
      throw new IllegalArgumentException(
          "The value '"
              + number
              + "' cannot be re represented as 64bit number (numeric overflow).");
    }

    if (unitLabel.isEmpty()) {
      return Duration.of(value, ChronoUnit.MILLIS);
    }

    ChronoUnit unit = LABEL_TO_UNIT_MAP.get(unitLabel);
    if (unit != null) {
      return Duration.of(value, unit);
    } else {
      throw new IllegalArgumentException(
          "Time interval unit label '"
              + unitLabel
              + "' does not match any of the recognized units: "
              + TimeUnit.getAllUnits());
    }
  }
