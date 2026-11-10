    private String normalizeHostName(String hostname) {
        checkNotNull(hostname, "hostname");
        if (hostname.isEmpty() || hostname.charAt(0) == '.') {
            throw new IllegalArgumentException("Hostname '" + hostname + "' not valid");
        }
        hostname = ImmutableDomainWildcardMapping.normalize(checkNotNull(hostname, "hostname"));
        if (hostname.charAt(0) == '*') {
            if (hostname.length() < 3 || hostname.charAt(1) != '.') {
                throw new IllegalArgumentException("Wildcard Hostname '" + hostname + "'not valid");
            }
            return hostname.substring(1);
        }
        return hostname;
    }
