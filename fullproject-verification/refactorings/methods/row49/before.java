	@Override
	public TerminalLayout getLayout(BigInteger index) {
		synchronized (lock) {
			if (BigInteger.ZERO.compareTo(index) <= 0 && index.compareTo(numIndexes) < 0) {
				return layouts.get(index.intValue());
			}
		}
		return null;
	}
