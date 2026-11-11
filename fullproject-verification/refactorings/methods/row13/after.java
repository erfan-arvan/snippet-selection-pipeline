    public static Class<?> getGenericClass(Class<?> cls, int i) {
        Type[] genericInterfaces = cls.getGenericInterfaces();
        if (genericInterfaces.length == 0 || !(genericInterfaces[0] instanceof ParameterizedType)) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!");
        }
        Type[] typeArguments = ((ParameterizedType) genericInterfaces[0]).getActualTypeArguments();
        if (i < 0 || i >= typeArguments.length) {
            throw new IllegalArgumentException(cls.getName() + " generic type undefined!");
        }
        Object genericClass = typeArguments[i];
        try {
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
