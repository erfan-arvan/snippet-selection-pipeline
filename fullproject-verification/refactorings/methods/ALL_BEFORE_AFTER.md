# Refactored methods: before / after

Original code is at the pinned commit of each repo; "after" is the same method with `../patches/<case>_*.patch` applied. Each case was checked with its checker: the target warning is reported before and gone after.

## row13: org.apache.dubbo.common.utils.ReflectUtils.getGenericClass

dubbo, index checker, warning `array.access.unsafe.high.constant,array.access.unsafe.low,array.access.unsafe.high`  
File: `dubbo-common/src/main/java/org/apache/dubbo/common/utils/ReflectUtils.java`

### Before
```java
    public static Class<?> getGenericClass(Class<?> cls, int i) {
        try {
            ParameterizedType parameterizedType = ((ParameterizedType) cls.getGenericInterfaces()[0]);
            Object genericClass = parameterizedType.getActualTypeArguments()[i];

            // handle nested generic type
            if (genericClass instanceof ParameterizedType) {
                return (Class<?>) ((ParameterizedType) genericClass).getRawType();
            }

            // handle array generic type
            if (genericClass instanceof GenericArrayType) {
                return (Class<?>) ((GenericArrayType) genericClass).getGenericComponentType();
            }

            // Requires JDK 7 or higher, Foo<int[]> is no longer GenericArrayType
            if (((Class) genericClass).isArray()) {
                return ((Class) genericClass).getComponentType();
            }
            return (Class<?>) genericClass;
        } catch (Throwable e) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!", e);
        }
    }
```

### After
```java
    public static Class<?> getGenericClass(Class<?> cls, int i) {
        try {
            Type[] genericInterfaces = cls.getGenericInterfaces();
            if (genericInterfaces.length == 0) {
                // Same exception the array access threw before; the catch below wraps it as before.
                throw new ArrayIndexOutOfBoundsException("Index 0 out of bounds for length 0");
            }
            ParameterizedType parameterizedType = ((ParameterizedType) genericInterfaces[0]);
            Type[] actualTypeArguments = parameterizedType.getActualTypeArguments();
            if (i < 0 || i >= actualTypeArguments.length) {
                throw new ArrayIndexOutOfBoundsException(
                        "Index " + i + " out of bounds for length " + actualTypeArguments.length);
            }
            Object genericClass = actualTypeArguments[i];

            // handle nested generic type
            if (genericClass instanceof ParameterizedType) {
                return (Class<?>) ((ParameterizedType) genericClass).getRawType();
            }

            // handle array generic type
            if (genericClass instanceof GenericArrayType) {
                return (Class<?>) ((GenericArrayType) genericClass).getGenericComponentType();
            }

            // Requires JDK 7 or higher, Foo<int[]> is no longer GenericArrayType
            if (((Class) genericClass).isArray()) {
                return ((Class) genericClass).getComponentType();
            }
            return (Class<?>) genericClass;
        } catch (Throwable e) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!", e);
        }
    }
```

## row16: org.apache.dubbo.common.utils.UrlUtils.isMatchGlobPattern

dubbo, index checker, warning `argument`  
File: `dubbo-common/src/main/java/org/apache/dubbo/common/utils/UrlUtils.java`

### Before
```java
    public static boolean isMatchGlobPattern(String pattern, String value) {
        if ("*".equals(pattern)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) && StringUtils.isEmpty(value)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) || StringUtils.isEmpty(value)) {
            return false;
        }

        int i = pattern.lastIndexOf('*');
        // doesn't find "*"
        if (i == -1) {
            return value.equals(pattern);
        }
        // "*" is at the end
        else if (i == pattern.length() - 1) {
            return value.startsWith(pattern.substring(0, i));
        }
        // "*" is at the beginning
        else if (i == 0) {
            return value.endsWith(pattern.substring(i + 1));
        }
        // "*" is in the middle
        else {
            String prefix = pattern.substring(0, i);
            String suffix = pattern.substring(i + 1);
            return value.startsWith(prefix) && value.endsWith(suffix);
        }
    }
```

### After
```java
    public static boolean isMatchGlobPattern(String pattern, String value) {
        if ("*".equals(pattern)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) && StringUtils.isEmpty(value)) {
            return true;
        }
        if (StringUtils.isEmpty(pattern) || StringUtils.isEmpty(value)) {
            return false;
        }

        int i = pattern.lastIndexOf('*');
        // doesn't find "*"
        if (i == -1) {
            return value.equals(pattern);
        }
        // "*" is at the end
        else if (i == pattern.length() - 1) {
            return value.startsWith(pattern.substring(0, i));
        }
        // "*" is at the beginning
        // (pattern.length() > 1 always holds here: i == 0 is a valid index, and the branch above
        // already handled i == pattern.length() - 1, so the length is not 1. Stating it lets the
        // checker see that substring(1) is in bounds.)
        else if (i == 0 && pattern.length() > 1) {
            return value.endsWith(pattern.substring(1));
        }
        // "*" is in the middle
        else {
            String prefix = pattern.substring(0, i);
            String suffix = pattern.substring(i + 1);
            return value.startsWith(prefix) && value.endsWith(suffix);
        }
    }
```

## row49: ghidra.app.plugin.core.terminal.TerminalLayoutModel.getLayout

ghidra, index checker, warning `argument`  
File: `Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/terminal/TerminalLayoutModel.java`

### Before
```java
	@Override
	public TerminalLayout getLayout(BigInteger index) {
		synchronized (lock) {
			if (BigInteger.ZERO.compareTo(index) <= 0 && index.compareTo(numIndexes) < 0) {
				return layouts.get(index.intValue());
			}
		}
		return null;
	}
```

### After
```java
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
```

## row53: ghidra.app.util.bin.format.macho.MachHeaderFlags.getFlags

ghidra, nullness checker, warning `unboxing.of.nullable`  
File: `Ghidra/Features/Base/src/main/java/ghidra/app/util/bin/format/macho/MachHeaderFlags.java`

### Before
```java
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
```

### After
```java
	public final static List<String> getFlags(int flags) {
		List<String> list = new ArrayList<>();
		Field[] fields = MachHeaderFlags.class.getDeclaredFields();
		for (Field field : fields) {
			if (field.getName().startsWith("MH_")) {
				try {
					Integer value = (Integer) field.get(null);
					// null used to throw NullPointerException here, which the catch below ignored
					if (value != null && (flags & value) != 0) {
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
```

## row54: ghidra.app.util.bin.format.macho.MachHeaderFlags.getFlags

ghidra, index checker, warning `argument`  
File: `Ghidra/Features/Base/src/main/java/ghidra/app/util/bin/format/macho/MachHeaderFlags.java`

### Before
```java
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
```

### After
```java
	public final static List<String> getFlags(int flags) {
		List<String> list = new ArrayList<>();
		Field[] fields = MachHeaderFlags.class.getDeclaredFields();
		for (Field field : fields) {
			String name = field.getName();
			if (name.startsWith("MH_")) {
				try {
					Integer value = (Integer) field.get(null);
					if ((flags & value) != 0) {
						list.add(name.substring("MH_".length()));
					}
				}
				catch (Exception e) {
					// do nothing
				}
			}
		}
		return list;
	}
```

## row90: ghidra.program.util.InstructionUtils.getFormatedInstructionObjects

ghidra, nullness checker, warning `toarray.nullable.elements.not.newarray`  
File: `Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/util/InstructionUtils.java`

### Before
```java
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
		String[] list = new String[set.size()];
		set.toArray(list);
		Arrays.sort(list, OBJSTRING_COMPARATOR);
		return list;
	}
```

### After
```java
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
```

## row95: ghidra.util.datastruct.ByteArray.get

ghidra, index checker, warning `array.access.unsafe.low`  
File: `Ghidra/Framework/Generic/src/main/java/ghidra/util/datastruct/ByteArray.java`

### Before
```java
    public byte get(int index) {
        if (index < bytes.length) {
            return bytes[index];
        }
        return (byte)0;
    }
```

### After
```java
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
```

## row114: org.apache.hudi.common.table.view.HoodieTableFileSystemView.fetchAllStoredFileGroups

hudi, nullness checker, warning `argument`  
File: `hudi-common/src/main/java/org/apache/hudi/common/table/view/HoodieTableFileSystemView.java`

### Before
```java
  @Override
  Stream<HoodieFileGroup> fetchAllStoredFileGroups(String partition) {
    List<HoodieFileGroup> fileGroups = partitionToFileGroupsMap.get(partition);
    if (fileGroups == null || fileGroups.isEmpty()) {
      LOG.warn("Partition: {} is not available in store", partition);
      return Stream.empty();
    }
    return new ArrayList<>(partitionToFileGroupsMap.get(partition)).stream();
  }
```

### After
```java
  @Override
  Stream<HoodieFileGroup> fetchAllStoredFileGroups(String partition) {
    List<HoodieFileGroup> fileGroups = partitionToFileGroupsMap.get(partition);
    if (fileGroups == null || fileGroups.isEmpty()) {
      LOG.warn("Partition: {} is not available in store", partition);
      return Stream.empty();
    }
    return new ArrayList<>(fileGroups).stream();
  }
```

## row153: io.netty.util.DomainWildcardMappingBuilder.normalizeHostName

netty, index checker, warning `argument`  
File: `common/src/main/java/io/netty/util/DomainWildcardMappingBuilder.java`

### Before
```java
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
```

### After
```java
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
```
