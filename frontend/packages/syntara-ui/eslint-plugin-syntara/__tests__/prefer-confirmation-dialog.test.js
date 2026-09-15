import { RuleTester } from 'eslint'
import { describe, it } from 'vitest'
import rule from '../rules/prefer-confirmation-dialog.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})

ruleTester.run('prefer-confirmation-dialog', rule, {
  valid: [
    // Modal without destructive title is fine
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Edit workflow" />
            <ModalBody>Content</ModalBody>
            <ModalFooter>
              <Button variant="primary">Save</Button>
            </ModalFooter>
          </Modal>
        );
      `,
    },
    // Modal with destructive title but no danger button
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Delete workflow" />
            <ModalBody>Are you sure?</ModalBody>
            <ModalFooter>
              <Button variant="primary">Confirm</Button>
            </ModalFooter>
          </Modal>
        );
      `,
    },
    // Modal with danger button but no destructive title
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Confirm action" />
            <ModalBody>Proceed?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Yes</Button>
            </ModalFooter>
          </Modal>
        );
      `,
    },
    // SynConfirmationDialog import present — entire file is skipped
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        import { SynConfirmationDialog } from '../components/dialogs/SynConfirmationDialog';
        const App = () => (
          <Modal>
            <ModalHeader title="Delete workflow" />
            <ModalBody>Are you sure?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Delete</Button>
            </ModalFooter>
          </Modal>
        );
      `,
    },
    // Non-PF Modal import is not tracked
    {
      code: `
        import { Modal } from 'some-other-library';
        const App = () => (
          <Modal>
            <ModalHeader title="Delete item" />
            <ModalBody>Sure?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Delete</Button>
            </ModalFooter>
          </Modal>
        );
      `,
    },
  ],
  invalid: [
    // Destructive title ("Delete") + danger button
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Delete workflow" />
            <ModalBody>Are you sure you want to delete this workflow?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Delete</Button>
              <Button variant="link">Cancel</Button>
            </ModalFooter>
          </Modal>
        );
      `,
      errors: [{ messageId: 'preferConfirmationDialog' }],
    },
    // Destructive title ("Remove") + danger button
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Remove credential" />
            <ModalBody>This cannot be undone.</ModalBody>
            <ModalFooter>
              <Button variant="danger">Remove</Button>
            </ModalFooter>
          </Modal>
        );
      `,
      errors: [{ messageId: 'preferConfirmationDialog' }],
    },
    // Destructive title with expression container + danger button
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title={"Stop execution"} />
            <ModalBody>Stop the running execution?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Stop</Button>
            </ModalFooter>
          </Modal>
        );
      `,
      errors: [{ messageId: 'preferConfirmationDialog' }],
    },
    // Destructive keyword "disconnect" + danger button
    {
      code: `
        import { Modal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <Modal>
            <ModalHeader title="Disconnect integration" />
            <ModalBody>This will disconnect the integration.</ModalBody>
            <ModalFooter>
              <Button variant="danger">Disconnect</Button>
            </ModalFooter>
          </Modal>
        );
      `,
      errors: [{ messageId: 'preferConfirmationDialog' }],
    },
    // Aliased Modal import with destructive pattern
    {
      code: `
        import { Modal as PfModal, ModalHeader, ModalBody, ModalFooter, Button } from '@patternfly/react-core';
        const App = () => (
          <PfModal>
            <ModalHeader title="Revoke access" />
            <ModalBody>Revoke all access?</ModalBody>
            <ModalFooter>
              <Button variant="danger">Revoke</Button>
            </ModalFooter>
          </PfModal>
        );
      `,
      errors: [{ messageId: 'preferConfirmationDialog' }],
    },
  ],
})
