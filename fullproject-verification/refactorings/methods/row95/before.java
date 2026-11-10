    public byte get(int index) {
        if (index < bytes.length) {
            return bytes[index];
        }
        return (byte)0;
    }
