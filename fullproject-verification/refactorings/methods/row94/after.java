	default Object[] collectBounds(B box) {
		List<Dimension<?, P, B>> dims = getDimensions();
		Object[] result = new Object[dims.size() * 2];
		Iterator<Dimension<?, P, B>> it = dims.iterator();
		for (int j = 0; j + 1 < result.length; j += 2) {
			Dimension<?, P, B> d = it.next();
			result[j] = d.lower(box);
			result[j + 1] = d.upper(box);
		}
		return result;
	}
