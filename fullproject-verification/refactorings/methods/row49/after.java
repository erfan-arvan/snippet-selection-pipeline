	@Override
	public TerminalLayout getLayout(BigInteger index) {
		synchronized (lock) {
			if (index.signum() >= 0 && index.compareTo(numIndexes) < 0) {
				int i = index.intValue();
				if (i < 0 || i >= layouts.size()) {
					// Same exception and message ArrayList.get(i) threw here before.
					throw new IndexOutOfBoundsException(
						"Index " + i + " out of bounds for length " + layouts.size());
				}
				return layouts.get(i);
			}
		}
		return null;
	}
