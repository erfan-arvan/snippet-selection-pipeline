    public byte get(int index) {
        if (index < 0) {
            // Same exception and message bytes[index] threw for a negative index before.
            throw new ArrayIndexOutOfBoundsException(
                "Index " + index + " out of bounds for length " + bytes.length);
        }
        if (index < bytes.length) {
            return bytes[index];
        }
        return (byte)0;
    }
