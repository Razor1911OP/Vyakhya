import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'
import { cx } from './cx'

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('scroll-thin overflow-x-auto', className)}>
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  )
}

export function Th({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cx('whitespace-nowrap border-b border-navy-700 px-3 py-2 text-2xs font-medium uppercase tracking-wider text-ink-400', className)} {...rest} />
}

export function Td({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx('border-b border-navy-800 px-3 py-2.5 align-top', className)} {...rest} />
}

export function Tr({ className, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cx('transition-colors', className)} {...rest} />
}
