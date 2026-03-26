from importlib import import_module

if __name__ == "__main__":
    main = import_module("pydantic_agents_playground.cli").main
    raise SystemExit(main())
