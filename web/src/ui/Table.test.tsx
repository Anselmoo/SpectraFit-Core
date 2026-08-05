import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Table } from "./Table";

afterEach(cleanup);

const columns = [
  { key: "backend", label: "Backend" },
  { key: "time", label: "Time (ms)", align: "right" as const },
];
const rows = [
  { backend: "lmfit", time: "842" },
  { backend: "jax", time: "143" },
];

describe("Table", () => {
  it("Table renders semantic table/thead/tbody with header labels and cell values", () => {
    const { container, getByText } = render(<Table columns={columns} rows={rows} />);
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelector("thead")).toBeTruthy();
    expect(container.querySelector("tbody")).toBeTruthy();
    getByText("Backend");
    getByText("Time (ms)");
    getByText("lmfit");
    getByText("143");
  });

  it("Table right-aligns a column when align is set", () => {
    const { container } = render(<Table columns={columns} rows={rows} />);
    const headers = container.querySelectorAll("th");
    expect(headers[1].style.textAlign).toBe("right");
  });

  it("Table renders one row per data entry", () => {
    const { container } = render(<Table columns={columns} rows={rows} />);
    expect(container.querySelectorAll("tbody tr").length).toBe(2);
  });

  it("Table dense tightens cell padding", () => {
    const { container: normal } = render(<Table columns={columns} rows={rows} />);
    const { container: dense } = render(<Table columns={columns} rows={rows} dense />);
    const normalCell = normal.querySelector("td");
    const denseCell = dense.querySelector("td");
    expect(normalCell?.style.padding).not.toBe(denseCell?.style.padding);
  });
});
