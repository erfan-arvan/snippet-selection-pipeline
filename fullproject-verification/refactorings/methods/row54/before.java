	public final static List<String> getFlags(int flags) {
		List<String> list = new ArrayList<>();
		Field[] fields = MachHeaderFlags.class.getDeclaredFields();
		for (Field field : fields) {
			if (field.getName().startsWith("MH_")) {
				try {
					Integer value = (Integer) field.get(null);
					if ((flags & value) != 0) {
						list.add(field.getName().substring("MH_".length()));
					}
				}
				catch (Exception e) {
					// do nothing
				}
			}
		}
		return list;
	}
