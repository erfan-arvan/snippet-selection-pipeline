    private String normalizeHostName(String hostname) {
        checkNotNull(hostname, "hostname");
        if (hostname.isEmpty() || hostname.charAt(0) == '.') {
            throw new IllegalArgumentException("Hostname '" + hostname + "' not valid");
        }
        hostname = ImmutableDomainWildcardMapping.normalize(checkNotNull(hostname, "hostname"));
        if (hostname.isEmpty()) {
            // normalize() can only return "" for unusual IDN input; charAt(0) threw exactly this before.
            throw new StringIndexOutOfBoundsException("index 0, length 0");
        }
        if (hostname.charAt(0) == '*') {
            if (hostname.length() < 3 || hostname.charAt(1) != '.') {
                throw new IllegalArgumentException("Wildcard Hostname '" + hostname + "'not valid");
            }
            return hostname.substring(1);
        }
        return hostname;
    }
