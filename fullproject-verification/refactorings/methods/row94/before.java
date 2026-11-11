	default Object[] collectBounds(B box) {
		List<Dimension<?, P, B>> dims = getDimensions();
		Object[] result = new Object[dims.size() * 2];
		for (int i = 0; i < dims.size(); i++) {
			Dimension<?, P, B> d = dims.get(i);
			result[i * 2] = d.lower(box);
			result[i * 2 + 1] = d.upper(box);
		}
		return result;
	}
