import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/no-nested-component-definitions.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

ruleTester.run('no-nested-component-definitions', rule, {
  valid: [
    // Arrow function component at module scope
    {
      code: `const Toggle = () => <Button />;`,
    },
    // Function declaration component at module scope
    {
      code: `function Dialog() { return <Modal />; }`,
    },
    // Lowercase helper function inside another function (not a component name)
    {
      code: `
        function ParentComponent() {
          const renderItem = (x) => <li>{x}</li>;
          return <ul>{renderItem('one')}</ul>;
        }
      `,
    },
    // Uppercase constant that is not a function
    {
      code: `
        function ParentComponent() {
          const MAX_COUNT = 100;
          return <div>{MAX_COUNT}</div>;
        }
      `,
    },
    // Uppercase variable assigned a non-function value inside a function
    {
      code: `
        function ParentComponent() {
          const Label = 'My Label';
          return <div>{Label}</div>;
        }
      `,
    },
    // Multiple module-scope components — no nesting involved
    {
      code: `
        const Header = () => <header />;
        const Footer = () => <footer />;
        function Page() {
          return (
            <div>
              <Header />
              <Footer />
            </div>
          );
        }
      `,
    },
    // Arrow function with no init (variable without assignment)
    {
      code: `
        function ParentComponent() {
          let Item;
          return <div />;
        }
      `,
    },
  ],
  invalid: [
    // Arrow function assigned to uppercase var inside a regular function
    {
      code: `
        function ParentComponent() {
          const InnerCard = () => <div className="card" />;
          return <InnerCard />;
        }
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }],
    },
    // Arrow function assigned to uppercase var inside a parent arrow component
    {
      code: `
        const ParentComponent = () => {
          const InnerCard = () => <div className="card" />;
          return <InnerCard />;
        };
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }],
    },
    // Function declaration with uppercase name inside a parent function
    {
      code: `
        function ParentComponent() {
          function Dialog() {
            return <div role="dialog" />;
          }
          return <Dialog />;
        }
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }],
    },
    // Nested component inside an arrow component (function expression variant)
    {
      code: `
        const ParentComponent = () => {
          const Row = function() { return <tr />; };
          return <table><tbody><Row /></tbody></table>;
        };
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }],
    },
    // Multiple nested components in one parent — produces two errors
    {
      code: `
        function ParentComponent() {
          const Header = () => <h1>Title</h1>;
          const Footer = () => <footer>End</footer>;
          return (
            <div>
              <Header />
              <Footer />
            </div>
          );
        }
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }, { messageId: 'noNestedComponentDefinition' }],
    },
    // Deeply nested: component inside component inside component
    {
      code: `
        function Outer() {
          function Middle() {
            const Inner = () => <span>deep</span>;
            return <Inner />;
          }
          return <Middle />;
        }
      `,
      errors: [{ messageId: 'noNestedComponentDefinition' }, { messageId: 'noNestedComponentDefinition' }],
    },
  ],
})
