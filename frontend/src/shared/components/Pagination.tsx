import { useState } from "react";
import { Button } from "./Button";
import "./pagination.css";

interface PaginationProps {
  label: string;
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
  pageSizes: readonly number[];
  disabled?: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

// 只组织后端页数的导航按钮，不筛选数据或计算业务统计。
function pageNumbers(page: number, count: number) {
  if (count <= 7) return Array.from({ length: count }, (_, index) => index + 1);
  const start = Math.min(Math.max(2, page - 2), count - 5);
  return [1, ...Array.from({ length: 5 }, (_, index) => start + index), count];
}

function PageJump({
  page,
  pageCount,
  disabled,
  onPageChange,
}: Pick<PaginationProps, "page" | "pageCount" | "disabled" | "onPageChange">) {
  const [value, setValue] = useState(String(page));
  return (
    <form
      className="ui-pagination__jump"
      onSubmit={(event) => {
        event.preventDefault();
        const next = Number(value);
        if (!disabled && Number.isInteger(next) && next >= 1 && next <= pageCount && next !== page)
          onPageChange(next);
      }}
    >
      <label>
        前往
        <input
          aria-label="跳转页码，按回车确认"
          type="number"
          min={1}
          max={pageCount}
          step={1}
          required
          value={value}
          disabled={disabled}
          onChange={(event) => setValue(event.target.value)}
        />
        页
      </label>
    </form>
  );
}

export function Pagination({
  label,
  total,
  page,
  pageCount,
  pageSize,
  pageSizes,
  disabled = false,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const numbers = pageNumbers(page, pageCount);
  const unavailable = disabled || total === 0;
  return (
    <nav className="ui-pagination" aria-label={label}>
      <div className="ui-pagination__size">
        <span>共 {total} 条</span>
        <select
          aria-label="每页条数"
          value={pageSize}
          disabled={disabled}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          {pageSizes.map((size) => (
            <option key={size} value={size}>
              {size}条/页
            </option>
          ))}
        </select>
      </div>
      <div className="ui-pagination__pages">
        <Button
          aria-label="上一页"
          disabled={unavailable || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" className="ui-pagination__previous">
            <path d="m6 4 4 4-4 4" />
          </svg>
        </Button>
        {numbers.map((number, index) => (
          <span className="ui-pagination__slot" key={number}>
            {index > 0 && number - numbers[index - 1] > 1 && (
              <span className="ui-pagination__ellipsis" aria-hidden="true">
                …
              </span>
            )}
            <Button
              aria-label={`第${number}页`}
              aria-current={number === page ? "page" : undefined}
              disabled={unavailable}
              onClick={() => {
                if (number !== page) onPageChange(number);
              }}
            >
              {number}
            </Button>
          </span>
        ))}
        <Button
          aria-label="下一页"
          disabled={unavailable || page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path d="m6 4 4 4-4 4" />
          </svg>
        </Button>
      </div>
      <PageJump
        key={`${page}-${pageCount}-${pageSize}`}
        page={page}
        pageCount={pageCount}
        disabled={unavailable}
        onPageChange={onPageChange}
      />
    </nav>
  );
}
