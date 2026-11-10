	private static String[] getFormatedInstructionObjects(Object[] objs) {
		if (objs == null) {
			return null;
		}
		HashSet<String> set = new HashSet<String>();
		for (Object element : objs) {
			if (element instanceof Scalar) {
				Scalar scalar = (Scalar) element;
				set.add("const:" + scalar.toString());
			}
			else if (element instanceof Register) {
				Register reg = (Register) element;
				set.add(reg.toString());
			}
			else if (element instanceof Address) {
				Address addr = (Address) element;
				set.add(addr.toString(true));
			}
		}
		String[] list = set.toArray(new String[set.size()]);
		Arrays.sort(list, OBJSTRING_COMPARATOR);
		return list;
	}
