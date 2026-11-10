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
