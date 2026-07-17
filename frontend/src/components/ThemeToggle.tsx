import { FiMoon, FiSun } from 'react-icons/fi'
import { useTheme } from '../theme'

const ThemeToggle = ({ className = '' }: { className?: string }) => {
    const { theme, toggleTheme } = useTheme()
    const isLight = theme === 'light'
    const targetTheme = isLight ? 'Dark' : 'Light'

    return (
        <button
            type="button"
            onClick={toggleTheme}
            className={`theme-toggle ${className}`}
            aria-label={`${targetTheme} Theme aktivieren`}
            title={`${targetTheme} Theme aktivieren`}
        >
            <span className="theme-toggle-icon" aria-hidden="true">
                {isLight ? <FiMoon /> : <FiSun />}
            </span>
            <span className="hidden xl:inline">{targetTheme}</span>
        </button>
    )
}

export default ThemeToggle
