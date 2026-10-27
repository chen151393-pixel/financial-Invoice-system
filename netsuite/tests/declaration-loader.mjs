import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

export function loader(native = {}, globals = {}) {
  const cache = new Map();
  function load(path) {
    const filename = resolve(path.endsWith(".js") ? path : path + ".js");
    if (cache.has(filename)) return cache.get(filename);
    let result;
    vm.runInNewContext(
      readFileSync(filename, "utf8"),
      {
        ...globals,
        define: (dependencies, factory) => {
          result = factory(
            ...dependencies.map((name) => {
              if (name.startsWith("N/")) {
                if (!(name in native)) throw new Error("不允许的 NS 依赖：" + name);
                return native[name];
              }
              return load(resolve(dirname(filename), name));
            }),
          );
        },
      },
      { filename },
    );
    cache.set(filename, result);
    return result;
  }
  return load;
}
